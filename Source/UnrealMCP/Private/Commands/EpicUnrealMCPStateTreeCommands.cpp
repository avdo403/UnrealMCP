#include "Commands/EpicUnrealMCPStateTreeCommands.h"
#include "Commands/EpicUnrealMCPCommonUtils.h"
#include "Components/StateTreeComponent.h"
#include "StateTree.h"
#include "VisualLogger/VisualLogger.h"
#include "GameFramework/Actor.h"

FEpicUnrealMCPStateTreeCommands::FEpicUnrealMCPStateTreeCommands()
{
}

TSharedPtr<FJsonObject> FEpicUnrealMCPStateTreeCommands::HandleCommand(const FString& CommandType, const TSharedPtr<FJsonObject>& Params)
{
    if (CommandType == TEXT("run_state_tree"))
    {
        return HandleRunStateTree(Params);
    }
    else if (CommandType == TEXT("send_state_tree_event"))
    {
        return HandleSendStateTreeEvent(Params);
    }
    else if (CommandType == TEXT("stop_state_tree"))
    {
        return HandleStopStateTree(Params);
    }

    return nullptr;
}

TSharedPtr<FJsonObject> FEpicUnrealMCPStateTreeCommands::HandleRunStateTree(const TSharedPtr<FJsonObject>& Params)
{
    FString ActorName;
    if (!Params->TryGetStringField(TEXT("actor_name"), ActorName))
    {
        return FEpicUnrealMCPCommonUtils::CreateErrorResponse(TEXT("Missing 'actor_name' parameter"));
    }

    FString StateTreePath;
    if (!Params->TryGetStringField(TEXT("state_tree_path"), StateTreePath))
    {
        return FEpicUnrealMCPCommonUtils::CreateErrorResponse(TEXT("Missing 'state_tree_path' parameter"));
    }

    AActor* Actor = FEpicUnrealMCPCommonUtils::FindActorByName(ActorName);
    if (!Actor)
    {
        return FEpicUnrealMCPCommonUtils::CreateErrorResponse(FString::Printf(TEXT("Actor not found: %s"), *ActorName));
    }

    UStateTreeComponent* STComp = Actor->FindComponentByClass<UStateTreeComponent>();
    if (!STComp)
    {
        // Add the component if it doesn't exist? For now, let's require it.
        return FEpicUnrealMCPCommonUtils::CreateErrorResponse(FString::Printf(TEXT("Actor %s has no StateTree component"), *ActorName));
    }

    UStateTree* ST = Cast<UStateTree>(StaticLoadObject(UStateTree::StaticClass(), nullptr, *StateTreePath));
    if (!ST)
    {
        return FEpicUnrealMCPCommonUtils::CreateErrorResponse(FString::Printf(TEXT("Failed to load StateTree: %s"), *StateTreePath));
    }

    STComp->SetStateTree(ST);
    STComp->StartLogic();

    TSharedPtr<FJsonObject> Result = MakeShared<FJsonObject>();
    Result->SetBoolField(TEXT("success"), true);
    Result->SetStringField(TEXT("message"), TEXT("StateTree started"));
    return Result;
}

TSharedPtr<FJsonObject> FEpicUnrealMCPStateTreeCommands::HandleSendStateTreeEvent(const TSharedPtr<FJsonObject>& Params)
{
    FString ActorName;
    if (!Params->TryGetStringField(TEXT("actor_name"), ActorName))
    {
        return FEpicUnrealMCPCommonUtils::CreateErrorResponse(TEXT("Missing 'actor_name' parameter"));
    }

    FString EventName;
    if (!Params->TryGetStringField(TEXT("event_name"), EventName))
    {
        return FEpicUnrealMCPCommonUtils::CreateErrorResponse(TEXT("Missing 'event_name' parameter"));
    }

    AActor* Actor = FEpicUnrealMCPCommonUtils::FindActorByName(ActorName);
    if (!Actor)
    {
        return FEpicUnrealMCPCommonUtils::CreateErrorResponse(FString::Printf(TEXT("Actor not found: %s"), *ActorName));
    }

    UStateTreeComponent* STComp = Actor->FindComponentByClass<UStateTreeComponent>();
    if (!STComp)
    {
        return FEpicUnrealMCPCommonUtils::CreateErrorResponse(FString::Printf(TEXT("Actor %s has no StateTree component"), *ActorName));
    }

    FStateTreeEvent Event;
    Event.Tag = FGameplayTag::RequestGameplayTag(FName(*EventName));
    
    STComp->SendStateTreeEvent(Event);

    TSharedPtr<FJsonObject> Result = MakeShared<FJsonObject>();
    Result->SetBoolField(TEXT("success"), true);
    Result->SetStringField(TEXT("event"), EventName);
    return Result;
}

TSharedPtr<FJsonObject> FEpicUnrealMCPStateTreeCommands::HandleStopStateTree(const TSharedPtr<FJsonObject>& Params)
{
    FString ActorName;
    if (!Params->TryGetStringField(TEXT("actor_name"), ActorName))
    {
        return FEpicUnrealMCPCommonUtils::CreateErrorResponse(TEXT("Missing 'actor_name' parameter"));
    }

    AActor* Actor = FEpicUnrealMCPCommonUtils::FindActorByName(ActorName);
    if (!Actor)
    {
        return FEpicUnrealMCPCommonUtils::CreateErrorResponse(FString::Printf(TEXT("Actor not found: %s"), *ActorName));
    }

    UStateTreeComponent* STComp = Actor->FindComponentByClass<UStateTreeComponent>();
    if (STComp)
    {
        STComp->StopLogic(TEXT("MCP Command"));
    }

    TSharedPtr<FJsonObject> Result = MakeShared<FJsonObject>();
    Result->SetBoolField(TEXT("success"), true);
    Result->SetStringField(TEXT("message"), TEXT("StateTree stopped"));
    return Result;
}
