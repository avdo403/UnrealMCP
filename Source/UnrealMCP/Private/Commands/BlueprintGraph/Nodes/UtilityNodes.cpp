#include "Commands/BlueprintGraph/Nodes/UtilityNodes.h"
#include "Commands/BlueprintGraph/Nodes/NodeCreatorUtils.h"
#include "K2Node_CallFunction.h"
#include "K2Node_Select.h"
#include "K2Node_SpawnActorFromClass.h"
#include "K2Node_MacroInstance.h"
#include "EdGraphSchema_K2.h"
#include "Kismet/KismetSystemLibrary.h"
#include "Kismet/KismetMathLibrary.h"
#include "Json.h"

UK2Node* FUtilityNodeCreator::CreatePrintNode(UEdGraph* Graph, const TSharedPtr<FJsonObject>& Params)
{
	if (!Graph || !Params.IsValid())
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

	// Set function reference BEFORE initialization
	PrintNode->SetFromFunction(PrintFunc);

	double PosX, PosY;
	FNodeCreatorUtils::ExtractNodePosition(Params, PosX, PosY);
	PrintNode->NodePosX = static_cast<int32>(PosX);
	PrintNode->NodePosY = static_cast<int32>(PosY);

	Graph->AddNode(PrintNode, true, false);
	FNodeCreatorUtils::InitializeK2Node(PrintNode, Graph);

	// Set message if provided AFTER initialization
	FString Message;
	if (Params->TryGetStringField(TEXT("message"), Message))
	{
		UEdGraphPin* InStringPin = PrintNode->FindPin(TEXT("InString"));
		if (InStringPin)
		{
			InStringPin->DefaultValue = Message;
		}
	}

	return PrintNode;
}

UK2Node* FUtilityNodeCreator::CreateCallFunctionNode(UEdGraph* Graph, const TSharedPtr<FJsonObject>& Params)
{
	if (!Graph || !Params.IsValid())
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

	// Find the function to call
	UFunction* TargetFunc = nullptr;
	FString ClassName;
	
	// First, check if this is a Blueprint function (in the same Blueprint)
	UBlueprint* BP = Cast<UBlueprint>(Graph->GetOuter());
	if (!BP && Graph->GetOuter())
	{
		// Try to get Blueprint from graph's outer
		BP = Cast<UBlueprint>(Graph->GetOuter()->GetOuter());
	}
	
	if (BP && BP->GeneratedClass)
	{
		// Try to find the function in the Blueprint's generated class
		TargetFunc = BP->GeneratedClass->FindFunctionByName(FName(*TargetFunction));
		
		if (TargetFunc)
		{
			// Set as self member since it's in the same Blueprint
			CallNode->FunctionReference.SetSelfMember(FName(*TargetFunction));
		}
	}
	
	// If not found in Blueprint, try external classes
	if (!TargetFunc)
	{
		if (Params->TryGetStringField(TEXT("target_class"), ClassName))
		{
			// Try to find or load the class
			UClass* TargetClass = LoadObject<UClass>(nullptr, *ClassName);
			if (!TargetClass && !ClassName.StartsWith(TEXT("/Script/")))
			{
				// Try with common prefixes if not a full path
				TArray<FString> Modules = { TEXT("Engine"), TEXT("CoreUObject"), TEXT("EnhancedInput") };
				for (const FString& Mod : Modules)
				{
					FString FullPath = FString::Printf(TEXT("/Script/%s.%s"), *Mod, *ClassName);
					TargetClass = LoadObject<UClass>(nullptr, *FullPath);
					if (TargetClass) break;
				}
			}

			if (TargetClass)
			{
				TargetFunc = TargetClass->FindFunctionByName(FName(*TargetFunction));
				if (!TargetFunc)
				{
					// Try with spaces in name (Unreal display name logic)
					FString SpacedName = TargetFunction.Replace(TEXT("_"), TEXT(" "));
					TargetFunc = TargetClass->FindFunctionByName(FName(*SpacedName));
				}

				if (TargetFunc)
				{
					CallNode->FunctionReference.SetExternalMember(FName(*TargetFunction), TargetClass);
					CallNode->SetFromFunction(TargetFunc);
				}
			}
		}
		else
		{
			// Try common Unreal classes (System Library AND Math Library)
			TargetFunc = UKismetSystemLibrary::StaticClass()->FindFunctionByName(FName(*TargetFunction));
			
			if (!TargetFunc)
			{
				TargetFunc = UKismetMathLibrary::StaticClass()->FindFunctionByName(FName(*TargetFunction));
			}

			if (TargetFunc)
			{
				CallNode->SetFromFunction(TargetFunc);
			}
		}
	}

	if (!TargetFunc)
	{
		// Better error logging
		UE_LOG(LogTemp, Warning, TEXT("Failed to find function '%s' in Blueprint, class '%s', or common libraries."), *TargetFunction, *ClassName);
		return nullptr;
	}

	double PosX, PosY;
	FNodeCreatorUtils::ExtractNodePosition(Params, PosX, PosY);
	CallNode->NodePosX = static_cast<int32>(PosX);
	CallNode->NodePosY = static_cast<int32>(PosY);

	Graph->AddNode(CallNode, true, false);
	FNodeCreatorUtils::InitializeK2Node(CallNode, Graph);

	return CallNode;
}

UK2Node* FUtilityNodeCreator::CreateSelectNode(UEdGraph* Graph, const TSharedPtr<FJsonObject>& Params)
{
	if (!Graph || !Params.IsValid())
	{
		return nullptr;
	}

	UK2Node_Select* SelectNode = NewObject<UK2Node_Select>(Graph);
	if (!SelectNode)
	{
		return nullptr;
	}

	double PosX, PosY;
	FNodeCreatorUtils::ExtractNodePosition(Params, PosX, PosY);
	SelectNode->NodePosX = static_cast<int32>(PosX);
	SelectNode->NodePosY = static_cast<int32>(PosY);

	Graph->AddNode(SelectNode, true, false);
	FNodeCreatorUtils::InitializeK2Node(SelectNode, Graph);

	// Initialize with a default type if provided (e.g. "bool", "int", "float")
	FString IndexType;
	if (Params->TryGetStringField(TEXT("index_type"), IndexType))
	{
		const UEdGraphSchema_K2* K2Schema = GetDefault<UEdGraphSchema_K2>();
		FEdGraphPinType PinType;
		PinType.PinCategory = *IndexType;
		
		// Map simple types to Unreal categories
		if (IndexType.Equals(TEXT("float"), ESearchCase::IgnoreCase)) PinType.PinCategory = UEdGraphSchema_K2::PC_Real;
		else if (IndexType.Equals(TEXT("int"), ESearchCase::IgnoreCase)) PinType.PinCategory = UEdGraphSchema_K2::PC_Int;
		else if (IndexType.Equals(TEXT("bool"), ESearchCase::IgnoreCase)) PinType.PinCategory = UEdGraphSchema_K2::PC_Boolean;
		
		UEdGraphPin* IndexPin = SelectNode->GetIndexPin();
		if (IndexPin)
		{
			IndexPin->PinType = PinType;
			SelectNode->PinConnectionListChanged(IndexPin);
			SelectNode->ReconstructNode();
		}
	}

	return SelectNode;
}

UK2Node* FUtilityNodeCreator::CreateSpawnActorNode(UEdGraph* Graph, const TSharedPtr<FJsonObject>& Params)
{
	if (!Graph || !Params.IsValid())
	{
		return nullptr;
	}

	UK2Node_SpawnActorFromClass* SpawnActorNode = NewObject<UK2Node_SpawnActorFromClass>(Graph);
	if (!SpawnActorNode)
	{
		return nullptr;
	}

	double PosX, PosY;
	FNodeCreatorUtils::ExtractNodePosition(Params, PosX, PosY);
	SpawnActorNode->NodePosX = static_cast<int32>(PosX);
	SpawnActorNode->NodePosY = static_cast<int32>(PosY);

	Graph->AddNode(SpawnActorNode, true, false);
	FNodeCreatorUtils::InitializeK2Node(SpawnActorNode, Graph);

	return SpawnActorNode;
}

UK2Node* FUtilityNodeCreator::CreateInterfaceCallNode(UEdGraph* Graph, const TSharedPtr<FJsonObject>& Params)
{
	if (!Graph || !Params.IsValid())
	{
		return nullptr;
	}

	FString FunctionName;
	if (!Params->TryGetStringField(TEXT("function_name"), FunctionName))
	{
		return nullptr;
	}

	UK2Node_CallFunction* CallNode = NewObject<UK2Node_CallFunction>(Graph);
	if (!CallNode)
	{
		return nullptr;
	}

	// Try to set the function if interface_class is provided
	FString InterfaceName;
	if (Params->TryGetStringField(TEXT("interface_class"), InterfaceName))
	{
		UClass* InterfaceClass = LoadObject<UClass>(nullptr, *InterfaceName);
		if (InterfaceClass)
		{
			CallNode->FunctionReference.SetExternalMember(FName(*FunctionName), InterfaceClass);
		}
	}
	
	double PosX, PosY;
	FNodeCreatorUtils::ExtractNodePosition(Params, PosX, PosY);
	CallNode->NodePosX = static_cast<int32>(PosX);
	CallNode->NodePosY = static_cast<int32>(PosY);

	Graph->AddNode(CallNode, true, false);
	FNodeCreatorUtils::InitializeK2Node(CallNode, Graph);

	return CallNode;
}

UK2Node* FUtilityNodeCreator::CreateMacroCallNode(UEdGraph* Graph, const TSharedPtr<FJsonObject>& Params)
{
	if (!Graph || !Params.IsValid())
	{
		return nullptr;
	}

	FString MacroName;
	if (!Params->TryGetStringField(TEXT("macro_name"), MacroName))
	{
		return nullptr;
	}

	UK2Node_MacroInstance* MacroNode = NewObject<UK2Node_MacroInstance>(Graph);
	if (!MacroNode)
	{
		return nullptr;
	}

	double PosX, PosY;
	FNodeCreatorUtils::ExtractNodePosition(Params, PosX, PosY);
	MacroNode->NodePosX = static_cast<int32>(PosX);
	MacroNode->NodePosY = static_cast<int32>(PosY);

	Graph->AddNode(MacroNode, true, false);
	FNodeCreatorUtils::InitializeK2Node(MacroNode, Graph);

	return MacroNode;
}

