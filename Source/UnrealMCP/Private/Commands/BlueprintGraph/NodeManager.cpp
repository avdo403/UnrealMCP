#include "Commands/BlueprintGraph/NodeManager.h"
#include "EpicUnrealMCPCommonUtils.h"
#include "Commands/BlueprintGraph/Nodes/ControlFlowNodes.h"
#include "Commands/BlueprintGraph/Nodes/DataNodes.h"
#include "Commands/BlueprintGraph/Nodes/UtilityNodes.h"
#include "Commands/BlueprintGraph/Nodes/CastingNodes.h"
#include "Commands/BlueprintGraph/Nodes/AnimationNodes.h"
#include "Commands/BlueprintGraph/Nodes/SpecializedNodes.h"
#include "Engine/Blueprint.h"
#include "EdGraph/EdGraph.h"
#include "EdGraphSchema_K2.h"
#include "K2Node_CallFunction.h"
#include "K2Node_Event.h"
#include "K2Node_VariableGet.h"
#include "K2Node_VariableSet.h"
#include "K2Node_InputKey.h"
#include "K2Node_PromotableOperator.h"
#include "K2Node_IfThenElse.h"
#include "Kismet2/BlueprintEditorUtils.h"
#include "Kismet2/KismetEditorUtilities.h"
#include "KismetCompiler.h"
#include "EditorAssetLibrary.h"
#include "Kismet/KismetSystemLibrary.h"
#include "Kismet/KismetMathLibrary.h"
#include "EdGraphUtilities.h"

TSharedPtr<FJsonObject> FBlueprintNodeManager::ImportNodesFromT3D(const TSharedPtr<FJsonObject>& Params)
{
    if (!Params.IsValid()) return CreateErrorResponse(TEXT("Invalid parameters"));

    FString BlueprintName;
    if (!Params->TryGetStringField(TEXT("blueprint_name"), BlueprintName))
        return CreateErrorResponse(TEXT("Missing 'blueprint_name' parameter"));

    FString T3DContent;
    if (!Params->TryGetStringField(TEXT("t3d_content"), T3DContent))
        return CreateErrorResponse(TEXT("Missing 't3d_content' parameter"));

    UBlueprint* BP = FEpicUnrealMCPCommonUtils::FindBlueprint(BlueprintName);
    if (!BP) return CreateErrorResponse(FString::Printf(TEXT("Blueprint not found: %s"), *BlueprintName));

    UEdGraph* Graph = BP->UbergraphPages.Num() > 0 ? BP->UbergraphPages[0] : nullptr;
    FString GraphName;
    if (Params->TryGetStringField(TEXT("graph_name"), GraphName) && !GraphName.IsEmpty())
    {
        for (UEdGraph* G : BP->FunctionGraphs) {
            if (G && G->GetName() == GraphName) { Graph = G; break; }
        }
    }

    if (!Graph) return CreateErrorResponse(TEXT("No valid target graph found"));

    TSet<UEdGraphNode*> ImportedNodes;
    FEdGraphUtilities::ImportNodesFromText(Graph, T3DContent, ImportedNodes);

    if (ImportedNodes.Num() == 0) return CreateErrorResponse(TEXT("Failed to import any nodes from T3D content"));

    // Apply offset if provided
    double PosX = 0, PosY = 0;
    Params->TryGetNumberField(TEXT("pos_x"), PosX);
    Params->TryGetNumberField(TEXT("pos_y"), PosY);

    TArray<TSharedPtr<FJsonValue>> NodeIds;
    for (UEdGraphNode* Node : ImportedNodes)
    {
        Node->NodePosX += (int32)PosX;
        Node->NodePosY += (int32)PosY;
        NodeIds.Add(MakeShareable(new FJsonValueString(Node->NodeGuid.ToString())));
    }

    FBlueprintEditorUtils::MarkBlueprintAsModified(BP);
    Graph->NotifyGraphChanged();

    TSharedPtr<FJsonObject> Response = MakeShareable(new FJsonObject);
    Response->SetBoolField(TEXT("success"), true);
    Response->SetArrayField(TEXT("imported_node_ids"), NodeIds);
    return Response;
}

TSharedPtr<FJsonObject> FBlueprintNodeManager::AddNode(const TSharedPtr<FJsonObject>& Params)
{
	// Validate parameters
	if (!Params.IsValid())
	{
		return CreateErrorResponse(TEXT("Invalid parameters"));
	}

	// Get required parameters
	FString BlueprintName;
	if (!Params->TryGetStringField(TEXT("blueprint_name"), BlueprintName))
	{
		return CreateErrorResponse(TEXT("Missing 'blueprint_name' parameter"));
	}

	FString NodeType;
	if (!Params->TryGetStringField(TEXT("node_type"), NodeType))
	{
		return CreateErrorResponse(TEXT("Missing 'node_type' parameter"));
	}

	// Get optional node parameters
	const TSharedPtr<FJsonObject>* NodeParamsPtr;
	TSharedPtr<FJsonObject> NodeParams;
	if (Params->TryGetObjectField(TEXT("node_params"), NodeParamsPtr))
	{
		NodeParams = *NodeParamsPtr;
	}
	else
	{
		NodeParams = MakeShareable(new FJsonObject);
	}

	// Load the Blueprint
	UBlueprint* BP = FEpicUnrealMCPCommonUtils::FindBlueprint(BlueprintName);
	if (!BP)
	{
		return CreateErrorResponse(FString::Printf(TEXT("Blueprint not found: %s"), *BlueprintName));
	}

	// Get the target graph (function graph or event graph)
	FString FunctionName;
	UEdGraph* Graph = nullptr;

	if (NodeParams->TryGetStringField(TEXT("function_name"), FunctionName) && !FunctionName.IsEmpty())
	{
		// Try to find the function graph
		for (UEdGraph* FuncGraph : BP->FunctionGraphs)
		{
			if (FuncGraph && (FuncGraph->GetFName().ToString() == FunctionName ||
							  (FuncGraph->GetOuter() && FuncGraph->GetOuter()->GetFName().ToString() == FunctionName)))
			{
				Graph = FuncGraph;
				break;
			}
		}

		if (!Graph)
		{
			// Fallback: partial match for auto-generated names
			for (UEdGraph* FuncGraph : BP->FunctionGraphs)
			{
				if (FuncGraph && FuncGraph->GetFName().ToString().Contains(FunctionName))
				{
					Graph = FuncGraph;
					break;
				}
			}
		}

		if (!Graph)
		{
			return CreateErrorResponse(FString::Printf(TEXT("Function graph not found: %s"), *FunctionName));
		}
	}
	else
	{
		// Use event graph if no function specified
		if (BP->UbergraphPages.Num() == 0)
		{
			return CreateErrorResponse(TEXT("Blueprint has no event graph"));
		}

		Graph = BP->UbergraphPages[0];
		if (!Graph)
		{
			return CreateErrorResponse(TEXT("Failed to get Blueprint event graph"));
		}
	}

	// Create node based on type - routed to specialized node creators
	UK2Node* NewNode = nullptr;

	// Control Flow Nodes
	if (NodeType.Equals(TEXT("Branch"), ESearchCase::IgnoreCase))
	{
		NewNode = FControlFlowNodeCreator::CreateBranchNode(Graph, NodeParams);
	}
	else if (NodeType.Equals(TEXT("Comparison"), ESearchCase::IgnoreCase))
	{
		NewNode = FControlFlowNodeCreator::CreateComparisonNode(Graph, NodeParams);
	}
	else if (NodeType.Equals(TEXT("Switch"), ESearchCase::IgnoreCase))
	{
		NewNode = FControlFlowNodeCreator::CreateSwitchNode(Graph, NodeParams);
	}
	else if (NodeType.Equals(TEXT("SwitchEnum"), ESearchCase::IgnoreCase))
	{
		NewNode = FControlFlowNodeCreator::CreateSwitchEnumNode(Graph, NodeParams);
	}
	else if (NodeType.Equals(TEXT("SwitchInteger"), ESearchCase::IgnoreCase))
	{
		NewNode = FControlFlowNodeCreator::CreateSwitchIntegerNode(Graph, NodeParams);
	}
	else if (NodeType.Equals(TEXT("ExecutionSequence"), ESearchCase::IgnoreCase))
	{
		NewNode = FControlFlowNodeCreator::CreateExecutionSequenceNode(Graph, NodeParams);
	}
	// Data Nodes
	else if (NodeType.Equals(TEXT("VariableGet"), ESearchCase::IgnoreCase))
	{
		NewNode = FDataNodeCreator::CreateVariableGetNode(Graph, NodeParams);
	}
	else if (NodeType.Equals(TEXT("VariableSet"), ESearchCase::IgnoreCase))
	{
		NewNode = FDataNodeCreator::CreateVariableSetNode(Graph, NodeParams);
	}
	else if (NodeType.Equals(TEXT("MakeArray"), ESearchCase::IgnoreCase))
	{
		NewNode = FDataNodeCreator::CreateMakeArrayNode(Graph, NodeParams);
	}
	// Utility Nodes
	else if (NodeType.Equals(TEXT("Print"), ESearchCase::IgnoreCase))
	{
		NewNode = FUtilityNodeCreator::CreatePrintNode(Graph, NodeParams);
	}
	else if (NodeType.Equals(TEXT("CallFunction"), ESearchCase::IgnoreCase))
	{
		NewNode = FUtilityNodeCreator::CreateCallFunctionNode(Graph, NodeParams);
	}
	else if (NodeType.Equals(TEXT("Select"), ESearchCase::IgnoreCase))
	{
		NewNode = FUtilityNodeCreator::CreateSelectNode(Graph, NodeParams);
	}
	else if (NodeType.Equals(TEXT("InterfaceCall"), ESearchCase::IgnoreCase))
	{
		NewNode = FUtilityNodeCreator::CreateInterfaceCallNode(Graph, NodeParams);
	}
	else if (NodeType.Equals(TEXT("MacroCall"), ESearchCase::IgnoreCase))
	{
		NewNode = FUtilityNodeCreator::CreateMacroCallNode(Graph, NodeParams);
	}
	else if (NodeType.Equals(TEXT("SpawnActor"), ESearchCase::IgnoreCase))
	{
		NewNode = FUtilityNodeCreator::CreateSpawnActorNode(Graph, NodeParams);
	}

	// Casting Nodes
	else if (NodeType.Equals(TEXT("DynamicCast"), ESearchCase::IgnoreCase))
	{
		NewNode = FCastingNodeCreator::CreateDynamicCastNode(Graph, NodeParams);
	}
	else if (NodeType.Equals(TEXT("ClassDynamicCast"), ESearchCase::IgnoreCase))
	{
		NewNode = FCastingNodeCreator::CreateClassDynamicCastNode(Graph, NodeParams);
	}
	else if (NodeType.Equals(TEXT("CastByteToEnum"), ESearchCase::IgnoreCase))
	{
		NewNode = FCastingNodeCreator::CreateCastByteToEnumNode(Graph, NodeParams);
	}
	// Animation Nodes
	else if (NodeType.Equals(TEXT("Timeline"), ESearchCase::IgnoreCase))
	{
		NewNode = FAnimationNodeCreator::CreateTimelineNode(Graph, NodeParams);
	}
	// Specialized Nodes
	else if (NodeType.Equals(TEXT("GetDataTableRow"), ESearchCase::IgnoreCase))
	{
		NewNode = FSpecializedNodeCreator::CreateGetDataTableRowNode(Graph, NodeParams);
	}
	else if (NodeType.Equals(TEXT("AddComponentByClass"), ESearchCase::IgnoreCase))
	{
		NewNode = FSpecializedNodeCreator::CreateAddComponentByClassNode(Graph, NodeParams);
	}
	else if (NodeType.Equals(TEXT("Self"), ESearchCase::IgnoreCase))
	{
		NewNode = FSpecializedNodeCreator::CreateSelfNode(Graph, NodeParams);
	}
	else if (NodeType.Equals(TEXT("ConstructObject"), ESearchCase::IgnoreCase))
	{
		NewNode = FSpecializedNodeCreator::CreateConstructObjectNode(Graph, NodeParams);
	}
	else if (NodeType.Equals(TEXT("Knot"), ESearchCase::IgnoreCase))
	{
		NewNode = FSpecializedNodeCreator::CreateKnotNode(Graph, NodeParams);
	}
	// Event nodes (kept for backward compatibility - should use add_event_node)
	else if (NodeType.Equals(TEXT("Event"), ESearchCase::IgnoreCase))
	{
		NewNode = CreateEventNode(Graph, NodeParams);
	}
	else
	{
		return CreateErrorResponse(FString::Printf(TEXT("Unknown node type: %s"), *NodeType));
	}

	if (!NewNode)
	{
		return CreateErrorResponse(FString::Printf(TEXT("Failed to create %s node"), *NodeType));
	}

	// Notify changes
	Graph->NotifyGraphChanged();
	FBlueprintEditorUtils::MarkBlueprintAsModified(BP);

	// Ensure node has a valid GUID
	if (NewNode->NodeGuid.IsValid() == false || NewNode->NodeGuid == FGuid())
	{
		NewNode->CreateNewGuid();
	}

	return CreateSuccessResponse(NewNode, NodeType);
}

TSharedPtr<FJsonObject> FBlueprintNodeManager::ResetNodePins(const TSharedPtr<FJsonObject>& Params)
{
	if (!Params.IsValid())
	{
		return CreateErrorResponse(TEXT("Invalid parameters"));
	}

	FString BlueprintName;
	if (!Params->TryGetStringField(TEXT("blueprint_name"), BlueprintName))
	{
		return CreateErrorResponse(TEXT("Missing 'blueprint_name' parameter"));
	}

	FString NodeId;
	if (!Params->TryGetStringField(TEXT("node_id"), NodeId))
	{
		return CreateErrorResponse(TEXT("Missing 'node_id' parameter"));
	}

	UBlueprint* BP = FEpicUnrealMCPCommonUtils::FindBlueprint(BlueprintName);
	if (!BP)
	{
		return CreateErrorResponse(FString::Printf(TEXT("Blueprint not found: %s"), *BlueprintName));
	}

	// Find the node
	UK2Node* TargetNode = nullptr;
	TArray<UEdGraph*> Graphs;
	Graphs.Append(BP->UbergraphPages);
	Graphs.Append(BP->FunctionGraphs);
	
	for (UEdGraph* Graph : Graphs)
	{
		for (UEdGraphNode* Node : Graph->Nodes)
		{
			if (Node && (Node->GetName() == NodeId || Node->NodeGuid.ToString() == NodeId))
			{
				TargetNode = Cast<UK2Node>(Node);
				break;
			}
		}
		if (TargetNode) break;
	}

	if (!TargetNode)
	{
		return CreateErrorResponse(FString::Printf(TEXT("Node not found: %s"), *NodeId));
	}

	// Reset pins
	TargetNode->ReconstructNode();
	
	FBlueprintEditorUtils::MarkBlueprintAsModified(BP);

	TSharedPtr<FJsonObject> Response = MakeShareable(new FJsonObject);
	Response->SetBoolField(TEXT("success"), true);
	Response->SetStringField(TEXT("node_id"), NodeId);
	return Response;
}

UK2Node* FBlueprintNodeManager::CreatePrintNode(UEdGraph* Graph, const TSharedPtr<FJsonObject>& Params)
{
	if (!Graph)
	{
		return nullptr;
	}

	UK2Node_CallFunction* PrintNode = NewObject<UK2Node_CallFunction>(Graph);
	if (!PrintNode)
	{
		return nullptr;
	}

	UFunction* PrintFunc = UKismetSystemLibrary::StaticClass()->FindFunctionByName(
		GET_FUNCTION_NAME_CHECKED(UKismetSystemLibrary, PrintString)
	);

	if (!PrintFunc)
	{
		return nullptr;
	}

	PrintNode->SetFromFunction(PrintFunc);

	// Set position
	double PosX = 0.0;
	double PosY = 0.0;
	Params->TryGetNumberField(TEXT("pos_x"), PosX);
	Params->TryGetNumberField(TEXT("pos_y"), PosY);

	PrintNode->NodePosX = static_cast<int32>(PosX);
	PrintNode->NodePosY = static_cast<int32>(PosY);

	PrintNode->AllocateDefaultPins();

	// Set message if provided
	FString Message;
	if (Params->TryGetStringField(TEXT("message"), Message))
	{
		UEdGraphPin* InStringPin = PrintNode->FindPin(TEXT("InString"));
		if (InStringPin)
		{
			InStringPin->DefaultValue = Message;
		}
	}

	Graph->AddNode(PrintNode, true, false);
	return PrintNode;
}

UK2Node* FBlueprintNodeManager::CreateEventNode(UEdGraph* Graph, const TSharedPtr<FJsonObject>& Params)
{
	if (!Graph)
	{
		return nullptr;
	}

	FString EventType;
	if (!Params->TryGetStringField(TEXT("event_type"), EventType))
	{
		EventType = TEXT("BeginPlay");
	}

	UK2Node* Node = nullptr;

	FKey Key(*EventType);
	if (Key.IsValid())
	{
		UK2Node_InputKey* InputKeyNode = NewObject<UK2Node_InputKey>(Graph);
		if (InputKeyNode)
		{
			InputKeyNode->InputKey = Key;
			Node = InputKeyNode;
		}
	}

	if (!Node)
	{
		UK2Node_Event* EventNode = NewObject<UK2Node_Event>(Graph);
		if (EventNode)
		{
			if (EventType.Equals(TEXT("BeginPlay"), ESearchCase::IgnoreCase))
			{
				EventNode->EventReference.SetExternalDelegateMember(FName(TEXT("ReceiveBeginPlay")));
				EventNode->bOverrideFunction = true;
			}
			else if (EventType.Equals(TEXT("Tick"), ESearchCase::IgnoreCase))
			{
				EventNode->EventReference.SetExternalDelegateMember(FName(TEXT("ReceiveTick")));
				EventNode->bOverrideFunction = true;
			}
			else
			{
				EventNode->CustomFunctionName = FName(*EventType);
			}
			Node = EventNode;
		}
	}

	if (!Node)
	{
		return nullptr;
	}

	double PosX = 0.0;
	double PosY = 0.0;
	Params->TryGetNumberField(TEXT("pos_x"), PosX);
	Params->TryGetNumberField(TEXT("pos_y"), PosY);

	Node->NodePosX = static_cast<int32>(PosX);
	Node->NodePosY = static_cast<int32>(PosY);

	Node->AllocateDefaultPins();
	Graph->AddNode(Node, true, false);

	return Node;
}

UK2Node* FBlueprintNodeManager::CreateVariableGetNode(UEdGraph* Graph, const TSharedPtr<FJsonObject>& Params)
{
	if (!Graph)
	{
		return nullptr;
	}

	FString VariableName;
	if (!Params->TryGetStringField(TEXT("variable_name"), VariableName))
	{
		return nullptr;
	}

	UK2Node_VariableGet* VarGetNode = NewObject<UK2Node_VariableGet>(Graph);
	if (!VarGetNode)
	{
		return nullptr;
	}

	VarGetNode->VariableReference.SetSelfMember(FName(*VariableName));

	double PosX = 0.0;
	double PosY = 0.0;
	Params->TryGetNumberField(TEXT("pos_x"), PosX);
	Params->TryGetNumberField(TEXT("pos_y"), PosY);

	VarGetNode->NodePosX = static_cast<int32>(PosX);
	VarGetNode->NodePosY = static_cast<int32>(PosY);

	VarGetNode->AllocateDefaultPins();
	Graph->AddNode(VarGetNode, true, false);

	return VarGetNode;
}

UK2Node* FBlueprintNodeManager::CreateVariableSetNode(UEdGraph* Graph, const TSharedPtr<FJsonObject>& Params)
{
	if (!Graph)
	{
		return nullptr;
	}

	FString VariableName;
	if (!Params->TryGetStringField(TEXT("variable_name"), VariableName))
	{
		return nullptr;
	}

	UK2Node_VariableSet* VarSetNode = NewObject<UK2Node_VariableSet>(Graph);
	if (!VarSetNode)
	{
		return nullptr;
	}

	VarSetNode->VariableReference.SetSelfMember(FName(*VariableName));

	double PosX = 0.0;
	double PosY = 0.0;
	Params->TryGetNumberField(TEXT("pos_x"), PosX);
	Params->TryGetNumberField(TEXT("pos_y"), PosY);

	VarSetNode->NodePosX = static_cast<int32>(PosX);
	VarSetNode->NodePosY = static_cast<int32>(PosY);

	VarSetNode->AllocateDefaultPins();
	Graph->AddNode(VarSetNode, true, false);

	return VarSetNode;
}

// LoadBlueprint removed - using FEpicUnrealMCPCommonUtils::FindBlueprint

UK2Node* FBlueprintNodeManager::CreateCallFunctionNode(UEdGraph* Graph, const TSharedPtr<FJsonObject>& Params)
{
	if (!Graph)
	{
		return nullptr;
	}

	// Get target function name
	FString TargetFunction;
	if (!Params->TryGetStringField(TEXT("target_function"), TargetFunction))
	{
		return nullptr;
	}

	UK2Node_CallFunction* CallNode = NewObject<UK2Node_CallFunction>(Graph);
	if (!CallNode)
	{
		return nullptr;
	}

	// Set position
	double PosX = 0.0;
	double PosY = 0.0;
	Params->TryGetNumberField(TEXT("pos_x"), PosX);
	Params->TryGetNumberField(TEXT("pos_y"), PosY);

	CallNode->NodePosX = static_cast<int32>(PosX);
	CallNode->NodePosY = static_cast<int32>(PosY);

	// Create GUID for the node
	CallNode->CreateNewGuid();

	// Set the function reference
	FString TargetClass;
	if (Params->TryGetStringField(TEXT("target_class"), TargetClass))
	{
		UClass* Cls = FindObject<UClass>(nullptr, *TargetClass);
		if (!Cls && !TargetClass.StartsWith(TEXT("/Script/")))
		{
			// Try with common prefixes if not a full path
			TArray<FString> Modules = { TEXT("Engine"), TEXT("CoreUObject") };
			for (const FString& Mod : Modules)
			{
				FString FullPath = FString::Printf(TEXT("/Script/%s.%s"), *Mod, *TargetClass);
				Cls = FindObject<UClass>(nullptr, *FullPath);
				if (Cls) break;
			}
		}

		if (Cls)
		{
			CallNode->FunctionReference.SetExternalMember(*TargetFunction, Cls);
		}
		else
		{
			CallNode->FunctionReference.SetSelfMember(*TargetFunction);
		}
	}
	else
	{
		CallNode->FunctionReference.SetSelfMember(*TargetFunction);
	}

	// Add node to graph with proper initialization
	Graph->AddNode(CallNode, true, false);

	// Post-place initialization
	CallNode->PostPlacedNewNode();

	// Allocate pins after all setup
	CallNode->AllocateDefaultPins();

	return CallNode;
}

UK2Node* FBlueprintNodeManager::CreateComparisonNode(UEdGraph* Graph, const TSharedPtr<FJsonObject>& Params)
{
	if (!Graph)
	{
		return nullptr;
	}

	// Create a Promotable Operator node for comparisons
	// Note: UK2Node_PromotableOperator in UE5.5 doesn't expose SetOperator() method
	// The node is created with default operator (Equal) and Unreal handles initialization
	UK2Node_PromotableOperator* ComparisonNode = NewObject<UK2Node_PromotableOperator>(Graph);
	if (!ComparisonNode)
	{
		return nullptr;
	}

	// Set position
	double PosX = 0.0;
	double PosY = 0.0;
	Params->TryGetNumberField(TEXT("pos_x"), PosX);
	Params->TryGetNumberField(TEXT("pos_y"), PosY);

	ComparisonNode->NodePosX = static_cast<int32>(PosX);
	ComparisonNode->NodePosY = static_cast<int32>(PosY);

	// Add to graph and initialize pins
	Graph->AddNode(ComparisonNode, false, false);
	ComparisonNode->CreateNewGuid();
	ComparisonNode->PostPlacedNewNode();
	ComparisonNode->AllocateDefaultPins();

	// Set pin type if specified (int, float, string, bool, etc.)
	FString PinType;
	if (Params->TryGetStringField(TEXT("pin_type"), PinType))
	{
		// Find and update the A and B pins to the specified type
		UEdGraphPin* PinA = ComparisonNode->FindPin(TEXT("A"));
		UEdGraphPin* PinB = ComparisonNode->FindPin(TEXT("B"));

		if (PinA && PinB)
		{
			// Create a proper FEdGraphPinType structure
			FEdGraphPinType NewPinType;

			if (PinType.Equals(TEXT("int"), ESearchCase::IgnoreCase))
			{
				NewPinType.PinCategory = UEdGraphSchema_K2::PC_Int;
			}
			else if (PinType.Equals(TEXT("float"), ESearchCase::IgnoreCase) || PinType.Equals(TEXT("double"), ESearchCase::IgnoreCase))
			{
				NewPinType.PinCategory = UEdGraphSchema_K2::PC_Real;
			}
			else if (PinType.Equals(TEXT("string"), ESearchCase::IgnoreCase))
			{
				NewPinType.PinCategory = UEdGraphSchema_K2::PC_String;
			}
			else if (PinType.Equals(TEXT("bool"), ESearchCase::IgnoreCase))
			{
				NewPinType.PinCategory = UEdGraphSchema_K2::PC_Boolean;
			}
			else if (PinType.Equals(TEXT("vector"), ESearchCase::IgnoreCase))
			{
				NewPinType.PinCategory = UEdGraphSchema_K2::PC_Struct;
				NewPinType.PinSubCategoryObject = TBaseStructure<FVector>::Get();
			}
			else if (PinType.Equals(TEXT("name"), ESearchCase::IgnoreCase))
			{
				NewPinType.PinCategory = UEdGraphSchema_K2::PC_Name;
			}
			else if (PinType.Equals(TEXT("text"), ESearchCase::IgnoreCase))
			{
				NewPinType.PinCategory = UEdGraphSchema_K2::PC_Text;
			}

			// Apply the entire pin type structure
			PinA->PinType = NewPinType;
			PinB->PinType = NewPinType;

			// Notify schema that pins have changed
			ComparisonNode->ReconstructNode();
		}
	}

	return ComparisonNode;
}

UK2Node* FBlueprintNodeManager::CreateBranchNode(UEdGraph* Graph, const TSharedPtr<FJsonObject>& Params)
{
	if (!Graph)
	{
		return nullptr;
	}

	// Create a Branch node using K2Node_IfThenElse
	UK2Node_IfThenElse* BranchNode = NewObject<UK2Node_IfThenElse>(Graph);
	if (!BranchNode)
	{
		return nullptr;
	}

	// Set position
	double PosX = 0.0;
	double PosY = 0.0;
	Params->TryGetNumberField(TEXT("pos_x"), PosX);
	Params->TryGetNumberField(TEXT("pos_y"), PosY);

	BranchNode->NodePosX = static_cast<int32>(PosX);
	BranchNode->NodePosY = static_cast<int32>(PosY);

	// Add to graph and initialize pins
	Graph->AddNode(BranchNode, false, false);
	BranchNode->CreateNewGuid();
	BranchNode->PostPlacedNewNode();
	BranchNode->AllocateDefaultPins();
	return BranchNode;
}

TSharedPtr<FJsonObject> FBlueprintNodeManager::CreateSuccessResponse(const UK2Node* Node, const FString& NodeType)
{
	TSharedPtr<FJsonObject> Response = MakeShareable(new FJsonObject);
	Response->SetBoolField(TEXT("success"), true);
	Response->SetStringField(TEXT("node_id"), Node->GetName());
	Response->SetStringField(TEXT("node_type"), NodeType);
	Response->SetNumberField(TEXT("pos_x"), Node->NodePosX);
	Response->SetNumberField(TEXT("pos_y"), Node->NodePosY);
	return Response;
}

TSharedPtr<FJsonObject> FBlueprintNodeManager::CreateErrorResponse(const FString& ErrorMessage)
{
	TSharedPtr<FJsonObject> Response = MakeShareable(new FJsonObject);
	Response->SetBoolField(TEXT("success"), false);
	Response->SetStringField(TEXT("error"), ErrorMessage);
	return Response;
}
