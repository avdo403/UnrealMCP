#include "Commands/BlueprintGraph/EventManager.h"
#include "EpicUnrealMCPCommonUtils.h"
#include "Engine/Blueprint.h"
#include "EdGraph/EdGraph.h"
#include "K2Node_Event.h"
#include "K2Node_InputKey.h"
#include "Kismet2/BlueprintEditorUtils.h"
#include "EditorAssetLibrary.h"
#include "AssetRegistry/AssetRegistryModule.h"
#include "InputCoreTypes.h"

TSharedPtr<FJsonObject> FEventManager::AddEventNode(const TSharedPtr<FJsonObject>& Params)
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

	FString EventName;
	if (!Params->TryGetStringField(TEXT("event_name"), EventName))
	{
		return CreateErrorResponse(TEXT("Missing 'event_name' parameter"));
	}

	// Get optional position parameters
	FVector2D Position(0.0f, 0.0f);
	double PosX = 0.0, PosY = 0.0;
	if (Params->TryGetNumberField(TEXT("pos_x"), PosX))
	{
		Position.X = static_cast<float>(PosX);
	}
	if (Params->TryGetNumberField(TEXT("pos_y"), PosY))
	{
		Position.Y = static_cast<float>(PosY);
	}

	// Load the Blueprint
	UBlueprint* Blueprint = FEpicUnrealMCPCommonUtils::FindBlueprint(BlueprintName);
	if (!Blueprint)
	{
		return CreateErrorResponse(FString::Printf(TEXT("Blueprint not found: %s"), *BlueprintName));
	}

	// Get the event graph (events can only exist in the event graph)
	if (Blueprint->UbergraphPages.Num() == 0)
	{
		return CreateErrorResponse(TEXT("Blueprint has no event graph"));
	}

	UEdGraph* Graph = Blueprint->UbergraphPages[0];
	if (!Graph)
	{
		return CreateErrorResponse(TEXT("Failed to get Blueprint event graph"));
	}

	// Create the node (Event or InputKey)
	UK2Node* NewNode = nullptr;
	
	// Check if this might be an Input Key node
	bool bIsInputKey = false;
	
	// If it's a short string or looks like a key name (doesn't start with Receive or Event)
	if (!EventName.StartsWith(TEXT("Receive")) && !EventName.StartsWith(TEXT("Event")))
	{
		FKey Key(*EventName);
		if (Key.IsValid())
		{
			bIsInputKey = true;
		}
	}

	if (bIsInputKey)
	{
		// Check for existing input key node
		UK2Node_InputKey* ExistingNode = nullptr;
		for (UEdGraphNode* Node : Graph->Nodes)
		{
			UK2Node_InputKey* KeyNode = Cast<UK2Node_InputKey>(Node);
			if (KeyNode && KeyNode->InputKey == FKey(*EventName))
			{
				ExistingNode = KeyNode;
				break;
			}
		}

		if (ExistingNode)
		{
			UE_LOG(LogTemp, Display, TEXT("F18: Using existing input key node '%s' (ID: %s)"),
				*EventName, *ExistingNode->NodeGuid.ToString());
			NewNode = ExistingNode;
		}
		else
		{
			UK2Node_InputKey* InputNode = NewObject<UK2Node_InputKey>(Graph);
			InputNode->InputKey = FKey(*EventName);
			InputNode->NodePosX = static_cast<int32>(Position.X);
			InputNode->NodePosY = static_cast<int32>(Position.Y);
			Graph->AddNode(InputNode, true);
			InputNode->PostPlacedNewNode();
			InputNode->AllocateDefaultPins();
			NewNode = InputNode;
			
			UE_LOG(LogTemp, Display, TEXT("F18: Created new input key node '%s' (ID: %s)"),
				*EventName, *InputNode->NodeGuid.ToString());
		}
	}
	else
	{
		NewNode = CreateEventNode(Graph, EventName, Position);
	}

	if (!NewNode)
	{
		return CreateErrorResponse(FString::Printf(TEXT("Failed to create node for: %s. Not a function or valid Key."), *EventName));
	}

	// Ensure node has a valid GUID
	if (!NewNode->NodeGuid.IsValid())
	{
		NewNode->CreateNewGuid();
	}

	// Notify changes
	Graph->NotifyGraphChanged();
	FBlueprintEditorUtils::MarkBlueprintAsModified(Blueprint);

	return CreateSuccessResponse(NewNode);
}

UK2Node_Event* FEventManager::CreateEventNode(UEdGraph* Graph, const FString& EventName, const FVector2D& Position)
{
	if (!Graph)
	{
		return nullptr;
	}

	UBlueprint* Blueprint = FBlueprintEditorUtils::FindBlueprintForGraph(Graph);
	if (!Blueprint)
	{
		return nullptr;
	}

	// Check for existing event node to avoid duplicates
	UK2Node_Event* ExistingNode = FindExistingEventNode(Graph, EventName);
	if (ExistingNode)
	{
		UE_LOG(LogTemp, Display, TEXT("F18: Using existing event node '%s' (ID: %s)"),
			*EventName, *ExistingNode->NodeGuid.ToString());
		return ExistingNode;
	}

	// Create new event node
	UK2Node_Event* EventNode = nullptr;
	UClass* BlueprintClass = Blueprint->GeneratedClass;

	if (!BlueprintClass)
	{
		UE_LOG(LogTemp, Error, TEXT("F18: Blueprint has no generated class"));
		return nullptr;
	}

	UFunction* EventFunction = BlueprintClass->FindFunctionByName(FName(*EventName));

	if (EventFunction)
	{
		EventNode = NewObject<UK2Node_Event>(Graph);
		EventNode->EventReference.SetExternalMember(FName(*EventName), BlueprintClass);
		EventNode->NodePosX = static_cast<int32>(Position.X);
		EventNode->NodePosY = static_cast<int32>(Position.Y);
		Graph->AddNode(EventNode, true);
		EventNode->PostPlacedNewNode();
		EventNode->AllocateDefaultPins();

		UE_LOG(LogTemp, Display, TEXT("F18: Created new event node '%s' (ID: %s)"),
			*EventName, *EventNode->NodeGuid.ToString());
	}
	else
	{
		UE_LOG(LogTemp, Error, TEXT("F18: Failed to find function for event name: %s"), *EventName);
	}

	return EventNode;
}

UK2Node_Event* FEventManager::FindExistingEventNode(UEdGraph* Graph, const FString& EventName)
{
	if (!Graph)
	{
		return nullptr;
	}

	for (UEdGraphNode* Node : Graph->Nodes)
	{
		UK2Node_Event* EventNode = Cast<UK2Node_Event>(Node);
		if (EventNode && EventNode->EventReference.GetMemberName() == FName(*EventName))
		{
			return EventNode;
		}
	}

	return nullptr;
}

// LoadBlueprint removed - using FEpicUnrealMCPCommonUtils::FindBlueprint

TSharedPtr<FJsonObject> FEventManager::CreateSuccessResponse(const UK2Node* Node)
{
	TSharedPtr<FJsonObject> Response = MakeShareable(new FJsonObject);
	Response->SetBoolField(TEXT("success"), true);
	Response->SetStringField(TEXT("node_id"), Node->NodeGuid.ToString());
	
	FString DisplayName = Node->GetName();
	if (const UK2Node_Event* EventNode = Cast<UK2Node_Event>(Node))
	{
		DisplayName = EventNode->EventReference.GetMemberName().ToString();
	}
	else if (const UK2Node_InputKey* InputNode = Cast<UK2Node_InputKey>(Node))
	{
		DisplayName = InputNode->InputKey.ToString();
	}

	Response->SetStringField(TEXT("event_name"), DisplayName);
	Response->SetNumberField(TEXT("pos_x"), Node->NodePosX);
	Response->SetNumberField(TEXT("pos_y"), Node->NodePosY);
	return Response;
}

TSharedPtr<FJsonObject> FEventManager::CreateErrorResponse(const FString& ErrorMessage)
{
	TSharedPtr<FJsonObject> Response = MakeShareable(new FJsonObject);
	Response->SetBoolField(TEXT("success"), false);
	Response->SetStringField(TEXT("error"), ErrorMessage);
	return Response;
}
