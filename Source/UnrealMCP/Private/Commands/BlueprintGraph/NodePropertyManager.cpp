#include "Commands/BlueprintGraph/NodePropertyManager.h"
#include "Commands/EpicUnrealMCPCommonUtils.h"
#include "Commands/BlueprintGraph/Nodes/SwitchEnumEditor.h"
#include "Commands/BlueprintGraph/Nodes/ExecutionSequenceEditor.h"
#include "Commands/BlueprintGraph/Nodes/MakeArrayEditor.h"
#include "Engine/Blueprint.h"
#include "EdGraph/EdGraph.h"
#include "EdGraph/EdGraphNode.h"
#include "EdGraph/EdGraphPin.h"
#include "EdGraphSchema_K2.h"
#include "K2Node_CallFunction.h"
#include "K2Node_VariableGet.h"
#include "K2Node_VariableSet.h"
#include "K2Node_Switch.h"
#include "K2Node_SwitchInteger.h"
#include "K2Node_SwitchEnum.h"
#include "K2Node_ExecutionSequence.h"
#include "K2Node_MakeArray.h"
#include "K2Node_PromotableOperator.h"
#include "K2Node_Select.h"
#include "K2Node_DynamicCast.h"
#include "K2Node_ClassDynamicCast.h"
#include "K2Node_CastByteToEnum.h"
#include "K2Node_Event.h"
#include "Kismet2/BlueprintEditorUtils.h"
#include "Kismet/KismetSystemLibrary.h"
#include "EditorAssetLibrary.h"
#include "Json.h"

TSharedPtr<FJsonObject> FNodePropertyManager::SetNodeProperty(const TSharedPtr<FJsonObject>& Params)
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

	FString NodeID;
	if (!Params->TryGetStringField(TEXT("node_id"), NodeID))
	{
		return CreateErrorResponse(TEXT("Missing 'node_id' parameter"));
	}

	// ===================================================
	// CHECK FOR SEMANTIC ACTION (new mode)
	// ===================================================
	FString Action;
	bool bHasAction = Params->HasField(TEXT("action"));

	if (bHasAction)
	{
		if (Params->TryGetStringField(TEXT("action"), Action))
		{
			if (!Action.IsEmpty())
			{
				// Semantic editing mode - delegate to EditNode
				return EditNode(Params);
			}
		}
	}

	// ===================================================
	// LEGACY MODE: Simple property modification
	// ===================================================
	FString PropertyName;
	if (!Params->TryGetStringField(TEXT("property_name"), PropertyName))
	{
		UE_LOG(LogTemp, Error, TEXT("SetNodeProperty: Missing 'property_name' parameter"));
		return CreateErrorResponse(TEXT("Missing 'property_name' parameter"));
	}

	if (!Params->HasField(TEXT("property_value")))
	{
		return CreateErrorResponse(TEXT("Missing 'property_value' parameter"));
	}

	TSharedPtr<FJsonValue> PropertyValue = Params->Values.FindRef(TEXT("property_value"));

	// Get optional function name
	FString FunctionName;
	Params->TryGetStringField(TEXT("function_name"), FunctionName);

	// Load the Blueprint
	UBlueprint* Blueprint = FEpicUnrealMCPCommonUtils::FindBlueprint(BlueprintName);
	if (!Blueprint)
	{
		return CreateErrorResponse(FString::Printf(TEXT("Blueprint not found: %s"), *BlueprintName));
	}

	// Get the appropriate graph
	UEdGraph* Graph = GetGraph(Blueprint, FunctionName);
	if (!Graph)
	{
		if (FunctionName.IsEmpty())
		{
			return CreateErrorResponse(TEXT("Blueprint has no event graph"));
		}
		else
		{
			return CreateErrorResponse(FString::Printf(TEXT("Function graph not found: %s"), *FunctionName));
		}
	}

	// Find the node
	UEdGraphNode* Node = FindNodeByID(Graph, NodeID);
	if (!Node)
	{
		return CreateErrorResponse(FString::Printf(TEXT("Node not found: %s"), *NodeID));
	}

	// Attempt to set property based on node type
	bool Success = false;

	// Try as Print node (UK2Node_CallFunction)
	UK2Node_CallFunction* CallFuncNode = Cast<UK2Node_CallFunction>(Node);
	if (CallFuncNode)
	{
		Success = SetPrintNodeProperty(CallFuncNode, PropertyName, PropertyValue);
	}

	// Try as Variable node
	if (!Success)
	{
		UK2Node* K2Node = Cast<UK2Node>(Node);
		if (K2Node)
		{
			Success = SetVariableNodeProperty(K2Node, PropertyName, PropertyValue);
		}
	}

	// Try generic properties
	if (!Success)
	{
		Success = SetGenericNodeProperty(Node, PropertyName, PropertyValue);
	}

	if (!Success)
	{
		return CreateErrorResponse(FString::Printf(
			TEXT("Failed to set property '%s' on node (property not supported or invalid value)"),
			*PropertyName));
	}

	// Notify changes
	Graph->NotifyGraphChanged();
	FBlueprintEditorUtils::MarkBlueprintAsModified(Blueprint);

	UE_LOG(LogTemp, Display,
		TEXT("Successfully set '%s' on node '%s' in %s"),
		*PropertyName, *NodeID, *BlueprintName);

	return CreateSuccessResponse(PropertyName);
}

TSharedPtr<FJsonObject> FNodePropertyManager::EditNode(const TSharedPtr<FJsonObject>& Params)
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

	FString NodeID;
	if (!Params->TryGetStringField(TEXT("node_id"), NodeID))
	{
		return CreateErrorResponse(TEXT("Missing 'node_id' parameter"));
	}

	FString Action;
	if (!Params->TryGetStringField(TEXT("action"), Action))
	{
		return CreateErrorResponse(TEXT("Missing 'action' parameter"));
	}

	// Get optional function name
	FString FunctionName;
	Params->TryGetStringField(TEXT("function_name"), FunctionName);

	// Load the Blueprint
	UBlueprint* Blueprint = FEpicUnrealMCPCommonUtils::FindBlueprint(BlueprintName);
	if (!Blueprint)
	{
		return CreateErrorResponse(FString::Printf(TEXT("Blueprint not found: %s"), *BlueprintName));
	}

	// Get the appropriate graph
	UEdGraph* Graph = GetGraph(Blueprint, FunctionName);
	if (!Graph)
	{
		if (FunctionName.IsEmpty())
		{
			return CreateErrorResponse(TEXT("Blueprint has no event graph"));
		}
		else
		{
			return CreateErrorResponse(FString::Printf(TEXT("Function graph not found: %s"), *FunctionName));
		}
	}

	// Find the node
	UEdGraphNode* Node = FindNodeByID(Graph, NodeID);
	if (!Node)
	{
		return CreateErrorResponse(FString::Printf(TEXT("Node not found: %s"), *NodeID));
	}

	// Cast to K2Node (edit operations require K2Node)
	UK2Node* K2Node = Cast<UK2Node>(Node);
	if (!K2Node)
	{
		return CreateErrorResponse(TEXT("Node is not a K2Node (cannot edit this node type)"));
	}

	// Dispatch the edit action
	return DispatchEditAction(K2Node, Graph, Action, Params);
}

TSharedPtr<FJsonObject> FNodePropertyManager::DispatchEditAction(
	UK2Node* Node,
	UEdGraph* Graph,
	const FString& Action,
	const TSharedPtr<FJsonObject>& Params)
{
	if (!Node || !Graph || !Params.IsValid())
	{
		return CreateErrorResponse(TEXT("Invalid node or graph"));
	}

	// === SWITCHENUM: Set enum type and auto-generate pins ===
	if (Action.Equals(TEXT("set_enum_type"), ESearchCase::IgnoreCase))
	{
		FString EnumPath;
		if (!Params->TryGetStringField(TEXT("enum_type"), EnumPath))
		{
			if (!Params->TryGetStringField(TEXT("enum_path"), EnumPath))
			{
				return CreateErrorResponse(TEXT("Missing 'enum_type' or 'enum_path' parameter"));
			}
		}

		bool bSuccess = FSwitchEnumEditor::SetEnumType(Node, Graph, EnumPath);
		if (bSuccess)
		{
			TSharedPtr<FJsonObject> Response = MakeShareable(new FJsonObject);
			Response->SetBoolField(TEXT("success"), true);
			Response->SetStringField(TEXT("action"), TEXT("set_enum_type"));
			Response->SetStringField(TEXT("enum_type"), EnumPath);
			return Response;
		}
		else
		{
			return CreateErrorResponse(FString::Printf(TEXT("Failed to set enum type: %s"), *EnumPath));
		}
	}

	// === EXECUTIONSEQUENCE/MAKEARRAY: Add pin ===
	if (Action.Equals(TEXT("add_pin"), ESearchCase::IgnoreCase))
	{
		bool bSuccess = FExecutionSequenceEditor::AddExecutionPin(Node, Graph);

		// If ExecutionSequence failed, try MakeArray
		if (!bSuccess)
		{
			bSuccess = FMakeArrayEditor::AddArrayElementPin(Node, Graph);
		}

		if (bSuccess)
		{
			TSharedPtr<FJsonObject> Response = MakeShareable(new FJsonObject);
			Response->SetBoolField(TEXT("success"), true);
			Response->SetStringField(TEXT("action"), TEXT("add_pin"));
			return Response;
		}
		else
		{
			return CreateErrorResponse(TEXT("Failed to add pin"));
		}
	}

	// === EXECUTIONSEQUENCE/MAKEARRAY: Remove pin ===
	if (Action.Equals(TEXT("remove_pin"), ESearchCase::IgnoreCase))
	{
		FString PinName;
		if (!Params->TryGetStringField(TEXT("pin_name"), PinName))
		{
			return CreateErrorResponse(TEXT("Missing 'pin_name' parameter"));
		}

		bool bSuccess = FExecutionSequenceEditor::RemoveExecutionPin(Node, Graph, PinName);
		if (!bSuccess)
		{
			// Try MakeArray if ExecutionSequence failed
			bSuccess = FMakeArrayEditor::RemoveArrayElementPin(Node, Graph, PinName);
		}

		if (bSuccess)
		{
			TSharedPtr<FJsonObject> Response = MakeShareable(new FJsonObject);
			Response->SetBoolField(TEXT("success"), true);
			Response->SetStringField(TEXT("action"), TEXT("remove_pin"));
			Response->SetStringField(TEXT("pin_name"), PinName);
			return Response;
		}
		else
		{
			return CreateErrorResponse(FString::Printf(TEXT("Failed to remove pin: %s"), *PinName));
		}
	}

	// === MAKEARRAY: Set number of array elements ===
	if (Action.Equals(TEXT("set_num_elements"), ESearchCase::IgnoreCase))
	{
		double NumElementsDouble = 0.0;
		if (!Params->TryGetNumberField(TEXT("num_elements"), NumElementsDouble))
		{
			return CreateErrorResponse(TEXT("Missing 'num_elements' parameter"));
		}
		int32 NumElements = static_cast<int32>(NumElementsDouble);

		bool bSuccess = FMakeArrayEditor::SetNumArrayElements(Node, Graph, NumElements);
		if (bSuccess)
		{
			TSharedPtr<FJsonObject> Response = MakeShareable(new FJsonObject);
			Response->SetBoolField(TEXT("success"), true);
			Response->SetStringField(TEXT("action"), TEXT("set_num_elements"));
			Response->SetNumberField(TEXT("num_elements"), NumElements);
			return Response;
		}
		else
		{
			return CreateErrorResponse(FString::Printf(TEXT("Failed to set array elements to %d"), NumElements));
		}
	}

	// ===================================================================
	// PHASE 2: TYPE MODIFICATION ACTIONS
	// ===================================================================

	// === K2Node_PromotableOperator: Set pin type ===
	if (Action.Equals(TEXT("set_pin_type"), ESearchCase::IgnoreCase))
	{
		FString PinName;
		if (!Params->TryGetStringField(TEXT("pin_name"), PinName))
		{
			return CreateErrorResponse(TEXT("Missing 'pin_name' parameter"));
		}

		FString NewType;
		if (!Params->TryGetStringField(TEXT("new_type"), NewType))
		{
			return CreateErrorResponse(TEXT("Missing 'new_type' parameter"));
		}

		// Build a FEdGraphPinType from the new_type string
		FEdGraphPinType PinType;
		if (NewType.Equals(TEXT("float"), ESearchCase::IgnoreCase) ||
			NewType.Equals(TEXT("real"), ESearchCase::IgnoreCase) ||
			NewType.Equals(TEXT("double"), ESearchCase::IgnoreCase))
		{
			PinType.PinCategory = UEdGraphSchema_K2::PC_Real;
			PinType.PinSubCategory = UEdGraphSchema_K2::PC_Float;
		}
		else if (NewType.Equals(TEXT("int"), ESearchCase::IgnoreCase) ||
			NewType.Equals(TEXT("integer"), ESearchCase::IgnoreCase))
		{
			PinType.PinCategory = UEdGraphSchema_K2::PC_Int;
		}
		else if (NewType.Equals(TEXT("bool"), ESearchCase::IgnoreCase) ||
			NewType.Equals(TEXT("boolean"), ESearchCase::IgnoreCase))
		{
			PinType.PinCategory = UEdGraphSchema_K2::PC_Boolean;
		}
		else if (NewType.Equals(TEXT("string"), ESearchCase::IgnoreCase))
		{
			PinType.PinCategory = UEdGraphSchema_K2::PC_String;
		}
		else if (NewType.Equals(TEXT("name"), ESearchCase::IgnoreCase))
		{
			PinType.PinCategory = UEdGraphSchema_K2::PC_Name;
		}
		else if (NewType.Equals(TEXT("vector"), ESearchCase::IgnoreCase))
		{
			PinType.PinCategory = UEdGraphSchema_K2::PC_Struct;
			PinType.PinSubCategoryObject = TBaseStructure<FVector>::Get();
		}
		else if (NewType.Equals(TEXT("rotator"), ESearchCase::IgnoreCase))
		{
			PinType.PinCategory = UEdGraphSchema_K2::PC_Struct;
			PinType.PinSubCategoryObject = TBaseStructure<FRotator>::Get();
		}
		else if (NewType.Equals(TEXT("transform"), ESearchCase::IgnoreCase))
		{
			PinType.PinCategory = UEdGraphSchema_K2::PC_Struct;
			PinType.PinSubCategoryObject = TBaseStructure<FTransform>::Get();
		}
		else
		{
			return CreateErrorResponse(FString::Printf(TEXT("Unsupported pin type: %s. Use: float, int, bool, string, name, vector"), *NewType));
		}

		UEdGraphPin* Pin = Node->FindPin(*PinName);
		if (!Pin)
		{
			// Try case-insensitive search
			for (UEdGraphPin* P : Node->Pins)
			{
				if (P && P->PinName.ToString().Equals(PinName, ESearchCase::IgnoreCase))
				{
					Pin = P;
					break;
				}
			}
		}

		if (!Pin)
		{
			return CreateErrorResponse(FString::Printf(TEXT("Pin '%s' not found on node"), *PinName));
		}

		Node->Modify();
		Pin->PinType = PinType;
		Node->ReconstructNode();
		Graph->NotifyGraphChanged();

		TSharedPtr<FJsonObject> Response = MakeShareable(new FJsonObject);
		Response->SetBoolField(TEXT("success"), true);
		Response->SetStringField(TEXT("action"), TEXT("set_pin_type"));
		Response->SetStringField(TEXT("pin_name"), PinName);
		Response->SetStringField(TEXT("new_type"), NewType);
		return Response;
	}

	// === K2Node_Select: Set value type ===
	if (Action.Equals(TEXT("set_value_type"), ESearchCase::IgnoreCase))
	{
		FString NewType;
		if (!Params->TryGetStringField(TEXT("new_type"), NewType))
		{
			return CreateErrorResponse(TEXT("Missing 'new_type' parameter"));
		}

		UK2Node_Select* SelectNode = Cast<UK2Node_Select>(Node);
		if (!SelectNode)
		{
			return CreateErrorResponse(TEXT("Node is not a K2Node_Select"));
		}

		FEdGraphPinType PinType;
		if (NewType.Equals(TEXT("float"), ESearchCase::IgnoreCase) ||
			NewType.Equals(TEXT("real"), ESearchCase::IgnoreCase))
		{
			PinType.PinCategory = UEdGraphSchema_K2::PC_Real;
			PinType.PinSubCategory = UEdGraphSchema_K2::PC_Float;
		}
		else if (NewType.Equals(TEXT("int"), ESearchCase::IgnoreCase))
		{
			PinType.PinCategory = UEdGraphSchema_K2::PC_Int;
		}
		else if (NewType.Equals(TEXT("bool"), ESearchCase::IgnoreCase))
		{
			PinType.PinCategory = UEdGraphSchema_K2::PC_Boolean;
		}
		else if (NewType.Equals(TEXT("string"), ESearchCase::IgnoreCase))
		{
			PinType.PinCategory = UEdGraphSchema_K2::PC_String;
		}
		else
		{
			return CreateErrorResponse(FString::Printf(TEXT("Unsupported value type: %s"), *NewType));
		}

		SelectNode->Modify();
		// Apply type to all value input pins
		for (UEdGraphPin* Pin : SelectNode->Pins)
		{
			if (Pin && Pin->Direction == EGPD_Input &&
				!Pin->PinName.ToString().Equals(TEXT("Index"), ESearchCase::IgnoreCase))
			{
				Pin->PinType = PinType;
			}
		}
		SelectNode->ReconstructNode();
		Graph->NotifyGraphChanged();

		TSharedPtr<FJsonObject> Response = MakeShareable(new FJsonObject);
		Response->SetBoolField(TEXT("success"), true);
		Response->SetStringField(TEXT("action"), TEXT("set_value_type"));
		Response->SetStringField(TEXT("new_type"), NewType);
		return Response;
	}

	// === K2Node_DynamicCast / K2Node_ClassDynamicCast: Set cast target ===
	if (Action.Equals(TEXT("set_cast_target"), ESearchCase::IgnoreCase))
	{
		FString TargetType;
		if (!Params->TryGetStringField(TEXT("target_type"), TargetType))
		{
			return CreateErrorResponse(TEXT("Missing 'target_type' parameter"));
		}

		// Try to find the target class
		UClass* TargetClass = FindObject<UClass>(nullptr, *TargetType);
		if (!TargetClass)
		{
			// Try with /Script/ prefix
			TargetClass = FindObject<UClass>(nullptr, *FString::Printf(TEXT("/Script/Engine.%s"), *TargetType));
		}
		if (!TargetClass)
		{
			// Try with /Game/ prefix
			TargetClass = LoadObject<UClass>(nullptr, *FString::Printf(TEXT("/Game/%s.%s_C"), *TargetType, *TargetType));
		}

		if (!TargetClass)
		{
			return CreateErrorResponse(FString::Printf(TEXT("Target class not found: %s"), *TargetType));
		}

		Node->Modify();

		UK2Node_DynamicCast* CastNode = Cast<UK2Node_DynamicCast>(Node);
		if (CastNode)
		{
			CastNode->TargetType = TargetClass;
			CastNode->ReconstructNode();
		}

		UK2Node_ClassDynamicCast* ClassCastNode = Cast<UK2Node_ClassDynamicCast>(Node);
		if (ClassCastNode)
		{
			ClassCastNode->TargetType = TargetClass;
			ClassCastNode->ReconstructNode();
		}

		if (!CastNode && !ClassCastNode)
		{
			return CreateErrorResponse(TEXT("Node is not a Cast node (K2Node_DynamicCast or K2Node_ClassDynamicCast)"));
		}

		Graph->NotifyGraphChanged();

		TSharedPtr<FJsonObject> Response = MakeShareable(new FJsonObject);
		Response->SetBoolField(TEXT("success"), true);
		Response->SetStringField(TEXT("action"), TEXT("set_cast_target"));
		Response->SetStringField(TEXT("target_type"), TargetType);
		return Response;
	}

	// ===================================================================
	// PHASE 3: REFERENCE UPDATES (DESTRUCTIVE)
	// ===================================================================

	// === K2Node_CallFunction: Change function being called ===
	if (Action.Equals(TEXT("set_function_call"), ESearchCase::IgnoreCase))
	{
		FString TargetFunction;
		if (!Params->TryGetStringField(TEXT("target_function"), TargetFunction))
		{
			return CreateErrorResponse(TEXT("Missing 'target_function' parameter"));
		}

		UK2Node_CallFunction* CallFuncNode = Cast<UK2Node_CallFunction>(Node);
		if (!CallFuncNode)
		{
			return CreateErrorResponse(TEXT("Node is not a K2Node_CallFunction"));
		}

		FString TargetClass;
		Params->TryGetStringField(TEXT("target_class"), TargetClass);

		// Try to find the function
		UClass* SearchClass = nullptr;
		if (!TargetClass.IsEmpty())
		{
			SearchClass = FindObject<UClass>(nullptr, *TargetClass);
			if (!SearchClass)
			{
				SearchClass = FindObject<UClass>(nullptr, *FString::Printf(TEXT("/Script/Engine.%s"), *TargetClass));
			}
		}

		UFunction* TargetFunctionObj = nullptr;
		if (SearchClass)
		{
			TargetFunctionObj = SearchClass->FindFunctionByName(FName(*TargetFunction));
		}

		if (!TargetFunctionObj)
		{
			// Search in all loaded classes
			for (TObjectIterator<UClass> It; It; ++It)
			{
				UFunction* Func = It->FindFunctionByName(FName(*TargetFunction));
				if (Func)
				{
					TargetFunctionObj = Func;
					break;
				}
			}
		}

		if (!TargetFunctionObj)
		{
			return CreateErrorResponse(FString::Printf(TEXT("Function not found: %s"), *TargetFunction));
		}

		Node->Modify();
		// Break all existing pin links (destructive operation)
		for (UEdGraphPin* Pin : Node->Pins)
		{
			if (Pin)
			{
				Pin->BreakAllPinLinks();
			}
		}
		CallFuncNode->SetFromFunction(TargetFunctionObj);
		CallFuncNode->ReconstructNode();
		Graph->NotifyGraphChanged();
		FBlueprintEditorUtils::MarkBlueprintAsStructurallyModified(FBlueprintEditorUtils::FindBlueprintForGraph(Graph));

		TSharedPtr<FJsonObject> Response = MakeShareable(new FJsonObject);
		Response->SetBoolField(TEXT("success"), true);
		Response->SetStringField(TEXT("action"), TEXT("set_function_call"));
		Response->SetStringField(TEXT("target_function"), TargetFunction);
		Response->SetStringField(TEXT("warning"), TEXT("All pin connections were cleared (destructive operation)"));
		return Response;
	}

	// === K2Node_Event: Change event type ===
	if (Action.Equals(TEXT("set_event_type"), ESearchCase::IgnoreCase))
	{
		FString EventType;
		if (!Params->TryGetStringField(TEXT("event_type"), EventType))
		{
			return CreateErrorResponse(TEXT("Missing 'event_type' parameter"));
		}

		UK2Node_Event* EventNode = Cast<UK2Node_Event>(Node);
		if (!EventNode)
		{
			return CreateErrorResponse(TEXT("Node is not a K2Node_Event"));
		}

		Node->Modify();
		// Break all existing pin links (destructive operation)
		for (UEdGraphPin* Pin : Node->Pins)
		{
			if (Pin)
			{
				Pin->BreakAllPinLinks();
			}
		}
		EventNode->EventReference.SetExternalMember(FName(*EventType), UObject::StaticClass());
		EventNode->ReconstructNode();
		Graph->NotifyGraphChanged();
		FBlueprintEditorUtils::MarkBlueprintAsStructurallyModified(FBlueprintEditorUtils::FindBlueprintForGraph(Graph));

		TSharedPtr<FJsonObject> Response = MakeShareable(new FJsonObject);
		Response->SetBoolField(TEXT("success"), true);
		Response->SetStringField(TEXT("action"), TEXT("set_event_type"));
		Response->SetStringField(TEXT("event_type"), EventType);
		Response->SetStringField(TEXT("warning"), TEXT("All pin connections were cleared (destructive operation)"));
		return Response;
	}

	// === All Nodes: Set pin default value ===
	if (Action.Equals(TEXT("set_pin_default_value"), ESearchCase::IgnoreCase))
	{
		FString PinName;
		if (!Params->TryGetStringField(TEXT("pin_name"), PinName))
		{
			return CreateErrorResponse(TEXT("Missing 'pin_name' parameter"));
		}

		FString PropertyValue;
		// Handle number correctly if it's not a string
		if (!Params->TryGetStringField(TEXT("property_value"), PropertyValue))
		{
			double NumVal = 0.0;
			if (Params->TryGetNumberField(TEXT("property_value"), NumVal)) 
			{
				PropertyValue = FString::SanitizeFloat(NumVal);
			}
			else 
			{
				return CreateErrorResponse(TEXT("Missing 'property_value' parameter or not convertible to string"));
			}
		}

		UEdGraphPin* TargetPin = Node->FindPin(*PinName);
		if (!TargetPin)
		{
			// Try case-insensitive
			for (UEdGraphPin* P : Node->Pins)
			{
				if (P && P->PinName.ToString().Equals(PinName, ESearchCase::IgnoreCase))
				{
					TargetPin = P;
					break;
				}
			}
		}

		if (!TargetPin)
		{
			return CreateErrorResponse(FString::Printf(TEXT("Pin '%s' not found on node"), *PinName));
		}

		Node->Modify();
		TargetPin->DefaultValue = PropertyValue;
		Node->ReconstructNode();
		Graph->NotifyGraphChanged();
		FBlueprintEditorUtils::MarkBlueprintAsModified(FBlueprintEditorUtils::FindBlueprintForGraph(Graph));

		TSharedPtr<FJsonObject> Response = MakeShareable(new FJsonObject);
		Response->SetBoolField(TEXT("success"), true);
		Response->SetStringField(TEXT("action"), TEXT("set_pin_default_value"));
		Response->SetStringField(TEXT("pin_name"), PinName);
		Response->SetStringField(TEXT("property_value"), PropertyValue);
		return Response;
	}

	// Unknown action
	return CreateErrorResponse(FString::Printf(TEXT("Unknown action: %s. Supported actions: set_enum_type, add_pin, remove_pin, set_num_elements, set_pin_type, set_value_type, set_cast_target, set_function_call, set_event_type, set_pin_default_value"), *Action));
}

bool FNodePropertyManager::SetPrintNodeProperty(
	UK2Node_CallFunction* PrintNode,
	const FString& PropertyName,
	const TSharedPtr<FJsonValue>& Value)
{
	if (!PrintNode || !Value.IsValid())
	{
		return false;
	}

	// Handle "message" property
	if (PropertyName.Equals(TEXT("message"), ESearchCase::IgnoreCase))
	{
		FString MessageValue;
		if (Value->TryGetString(MessageValue))
		{
			UEdGraphPin* InStringPin = PrintNode->FindPin(TEXT("InString"));
			if (InStringPin)
			{
				InStringPin->DefaultValue = MessageValue;
				return true;
			}
		}
	}

	// Handle "duration" property
	if (PropertyName.Equals(TEXT("duration"), ESearchCase::IgnoreCase))
	{
		double DurationValue;
		if (Value->TryGetNumber(DurationValue))
		{
			UEdGraphPin* DurationPin = PrintNode->FindPin(TEXT("Duration"));
			if (DurationPin)
			{
				DurationPin->DefaultValue = FString::SanitizeFloat(DurationValue);
				return true;
			}
		}
	}

	return false;
}

bool FNodePropertyManager::SetVariableNodeProperty(
	UK2Node* VarNode,
	const FString& PropertyName,
	const TSharedPtr<FJsonValue>& Value)
{
	if (!VarNode || !Value.IsValid())
	{
		return false;
	}

	// Handle "variable_name" property
	if (PropertyName.Equals(TEXT("variable_name"), ESearchCase::IgnoreCase))
	{
		FString VarName;
		if (Value->TryGetString(VarName))
		{
			UK2Node_VariableGet* VarGet = Cast<UK2Node_VariableGet>(VarNode);
			if (VarGet)
			{
				VarGet->VariableReference.SetSelfMember(FName(*VarName));
				VarGet->ReconstructNode();
				return true;
			}

			UK2Node_VariableSet* VarSet = Cast<UK2Node_VariableSet>(VarNode);
			if (VarSet)
			{
				VarSet->VariableReference.SetSelfMember(FName(*VarName));
				VarSet->ReconstructNode();
				return true;
			}
		}
	}

	return false;
}

bool FNodePropertyManager::SetGenericNodeProperty(
	UEdGraphNode* Node,
	const FString& PropertyName,
	const TSharedPtr<FJsonValue>& Value)
{
	if (!Node || !Value.IsValid())
	{
		return false;
	}

	// Handle "pos_x" property
	if (PropertyName.Equals(TEXT("pos_x"), ESearchCase::IgnoreCase))
	{
		double PosX;
		if (Value->TryGetNumber(PosX))
		{
			Node->NodePosX = static_cast<int32>(PosX);
			return true;
		}
	}

	// Handle "pos_y" property
	if (PropertyName.Equals(TEXT("pos_y"), ESearchCase::IgnoreCase))
	{
		double PosY;
		if (Value->TryGetNumber(PosY))
		{
			Node->NodePosY = static_cast<int32>(PosY);
			return true;
		}
	}

	// Handle "comment" property
	if (PropertyName.Equals(TEXT("comment"), ESearchCase::IgnoreCase))
	{
		FString Comment;
		if (Value->TryGetString(Comment))
		{
			Node->NodeComment = Comment;
			return true;
		}
	}

	// Handle "pin_default:[PinName]" property
	if (PropertyName.StartsWith(TEXT("pin_default:")))
	{
		FString PinName = PropertyName.RightChop(12);
		FString Val;
		
		// Attempt to get string representation of the JSON value
		if (Value->Type == EJson::String)
		{
			Val = Value->AsString();
		}
		else if (Value->Type == EJson::Boolean)
		{
			Val = Value->AsBool() ? TEXT("true") : TEXT("false");
		}
		else if (Value->Type == EJson::Number)
		{
			// For floats/ints, SanitizeFloat is generally safe for Blueprint default values
			Val = FString::SanitizeFloat(Value->AsNumber());
			// If it's effectively an integer, remove the trailing .0 for cleaner values
			if (Val.EndsWith(TEXT(".0")))
			{
				Val.LeftChopInline(2);
			}
		}
		else if (Value->Type == EJson::Array)
		{
			// For vectors/rotators/colors, we expect a string in format "(X=0.0,Y=0.0,Z=0.0)"
			// But if passed as JSON array, we can attempt to format it
			const TArray<TSharedPtr<FJsonValue>>& Array = Value->AsArray();
			if (Array.Num() == 3) // Vector/Rotator
			{
				Val = FString::Printf(TEXT("(X=%f,Y=%f,Z=%f)"), Array[0]->AsNumber(), Array[1]->AsNumber(), Array[2]->AsNumber());
			}
			else if (Array.Num() == 4) // Color
			{
				Val = FString::Printf(TEXT("(R=%f,G=%f,B=%f,A=%f)"), Array[0]->AsNumber(), Array[1]->AsNumber(), Array[2]->AsNumber(), Array[3]->AsNumber());
			}
		}

		if (!Val.IsEmpty() || Value->Type == EJson::String)
		{
			UEdGraphPin* Pin = Node->FindPin(*PinName);
			if (!Pin)
			{
				// Try case-insensitive search
				for (UEdGraphPin* P : Node->Pins)
				{
					if (P->PinName.ToString().Equals(PinName, ESearchCase::IgnoreCase))
					{
						Pin = P;
                        break;
					}
				}
			}

			if (Pin)
			{
				Pin->DefaultValue = Val;
				return true;
			}
		}
		else if (Value->Type == EJson::Boolean)
		{
			UEdGraphPin* Pin = Node->FindPin(*PinName);
			if (Pin)
			{
				Pin->DefaultValue = Value->AsBool() ? TEXT("true") : TEXT("false");
				return true;
			}
		}
		else if (Value->Type == EJson::Number)
		{
			UEdGraphPin* Pin = Node->FindPin(*PinName);
			if (Pin)
			{
				Pin->DefaultValue = FString::SanitizeFloat(Value->AsNumber());
				return true;
			}
		}
		else if (Value->Type == EJson::Array)
		{
			UEdGraphPin* Pin = Node->FindPin(*PinName);
			if (Pin)
			{
				const TArray<TSharedPtr<FJsonValue>>& Array = Value->AsArray();
				if (Array.Num() >= 3)
				{
					Pin->DefaultValue = FString::Printf(TEXT("(X=%f,Y=%f,Z=%f)"), 
						Array[0]->AsNumber(), Array[1]->AsNumber(), Array[2]->AsNumber());
					return true;
				}
			}
		}
	}

	return false;
}

UEdGraph* FNodePropertyManager::GetGraph(UBlueprint* Blueprint, const FString& FunctionName)
{
	if (!Blueprint)
	{
		return nullptr;
	}

	// If no function name, return EventGraph
	if (FunctionName.IsEmpty())
	{
		if (Blueprint->UbergraphPages.Num() > 0)
		{
			return Blueprint->UbergraphPages[0];
		}
		return nullptr;
	}

	// Search in function graphs
	for (UEdGraph* FuncGraph : Blueprint->FunctionGraphs)
	{
		if (FuncGraph && FuncGraph->GetName().Equals(FunctionName, ESearchCase::IgnoreCase))
		{
			return FuncGraph;
		}
	}

	return nullptr;
}

UEdGraphNode* FNodePropertyManager::FindNodeByID(UEdGraph* Graph, const FString& NodeID)
{
	if (!Graph)
	{
		return nullptr;
	}

	for (UEdGraphNode* Node : Graph->Nodes)
	{
		if (!Node)
		{
			continue;
		}

		// Try matching by NodeGuid
		if (Node->NodeGuid.ToString().Equals(NodeID, ESearchCase::IgnoreCase))
		{
			return Node;
		}

		// Try matching by GetName()
		if (Node->GetName().Equals(NodeID, ESearchCase::IgnoreCase))
		{
			return Node;
		}
	}

	return nullptr;
}



TSharedPtr<FJsonObject> FNodePropertyManager::CreateSuccessResponse(const FString& PropertyName)
{
	TSharedPtr<FJsonObject> Response = MakeShareable(new FJsonObject);
	Response->SetBoolField(TEXT("success"), true);
	Response->SetStringField(TEXT("updated_property"), PropertyName);
	return Response;
}

TSharedPtr<FJsonObject> FNodePropertyManager::CreateErrorResponse(const FString& ErrorMessage)
{
	TSharedPtr<FJsonObject> Response = MakeShareable(new FJsonObject);
	Response->SetBoolField(TEXT("success"), false);
	Response->SetStringField(TEXT("error"), ErrorMessage);
	return Response;
}
