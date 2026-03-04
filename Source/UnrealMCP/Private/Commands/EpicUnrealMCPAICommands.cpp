#include "Commands/EpicUnrealMCPAICommands.h"
#include "Commands/EpicUnrealMCPCommonUtils.h"
#include "AIController.h"
#include "BehaviorTree/BlackboardComponent.h"
#include "BehaviorTree/BehaviorTree.h"
#include "Perception/AIPerceptionComponent.h"
#include "Perception/AIPerceptionTypes.h"
#include "Perception/AISense_Sight.h"
#include "NavigationSystem.h"
#include "Navigation/PathFollowingComponent.h"
#include "EnvironmentQuery/EnvQueryManager.h"
#include "EnvironmentQuery/EnvQueryTypes.h"
#include "EnvironmentQuery/EnvQuery.h"
#include "EnvironmentQuery/Items/EnvQueryItemType_Actor.h"
#include "Blueprint/AIBlueprintHelperLibrary.h"
#include "Engine/World.h"
#include "GameFramework/Pawn.h"
#include "Editor.h"

FEpicUnrealMCPAICommands::FEpicUnrealMCPAICommands()
{
}

TSharedPtr<FJsonObject> FEpicUnrealMCPAICommands::HandleCommand(const FString& CommandType, const TSharedPtr<FJsonObject>& Params)
{
    if (CommandType == TEXT("ai_move_to"))
    {
        return HandleAIMoveTo(Params);
    }
    else if (CommandType == TEXT("run_behavior_tree"))
    {
        return HandleRunBehaviorTree(Params);
    }
    else if (CommandType == TEXT("set_blackboard_value"))
    {
        return HandleSetBlackboardValue(Params);
    }
    else if (CommandType == TEXT("get_perception_info"))
    {
        return HandleGetPerceptionInfo(Params);
    }
    else if (CommandType == TEXT("register_perception_source"))
    {
        return HandleRegisterPerceptionSource(Params);
    }
    else if (CommandType == TEXT("get_ai_status"))
    {
        return HandleGetAIStatus(Params);
    }
    else if (CommandType == TEXT("stop_ai_movement"))
    {
        return HandleStopAIMovement(Params);
    }
    else if (CommandType == TEXT("get_random_reachable_point"))
    {
        return HandleGetRandomReachablePoint(Params);
    }
    else if (CommandType == TEXT("run_eqs_query"))
    {
        return HandleRunEQSQuery(Params);
    }

    return FEpicUnrealMCPCommonUtils::CreateErrorResponse(FString::Printf(TEXT("Unknown AI command: %s"), *CommandType));
}

TSharedPtr<FJsonObject> FEpicUnrealMCPAICommands::HandleAIMoveTo(const TSharedPtr<FJsonObject>& Params)
{
    FString PawnName;
    if (!Params->TryGetStringField(TEXT("pawn_name"), PawnName))
    {
        return FEpicUnrealMCPCommonUtils::CreateErrorResponse(TEXT("Missing 'pawn_name' parameter"));
    }

    AActor* PawnActor = FEpicUnrealMCPCommonUtils::FindActorByName(PawnName);
    APawn* Pawn = Cast<APawn>(PawnActor);
    if (!Pawn)
    {
        return FEpicUnrealMCPCommonUtils::CreateErrorResponse(FString::Printf(TEXT("Pawn not found or is not a Pawn: %s"), *PawnName));
    }

    AAIController* AIC = Cast<AAIController>(Pawn->GetController());
    if (!AIC)
    {
        return FEpicUnrealMCPCommonUtils::CreateErrorResponse(FString::Printf(TEXT("Pawn %s does not have an AI Controller"), *PawnName));
    }

    float AcceptanceRadius = 5.0f;
    Params->TryGetNumberField(TEXT("acceptance_radius"), AcceptanceRadius);

    bool bStopOnOverlap = true;
    Params->TryGetBoolField(TEXT("stop_on_overlap"), bStopOnOverlap);

    // Target can be either a location or another actor
    if (Params->HasField(TEXT("target_actor")))
    {
        FString TargetActorName = Params->GetStringField(TEXT("target_actor"));
        AActor* TargetActor = FEpicUnrealMCPCommonUtils::FindActorByName(TargetActorName);
        if (!TargetActor)
        {
            return FEpicUnrealMCPCommonUtils::CreateErrorResponse(FString::Printf(TEXT("Target actor not found: %s"), *TargetActorName));
        }

        AIC->MoveToActor(TargetActor, AcceptanceRadius, bStopOnOverlap);
        
        TSharedPtr<FJsonObject> Result = MakeShared<FJsonObject>();
        Result->SetStringField(TEXT("status"), TEXT("Moving to actor"));
        Result->SetStringField(TEXT("target"), TargetActorName);
        return Result;
    }
    else if (Params->HasField(TEXT("location")))
    {
        FVector Location = FEpicUnrealMCPCommonUtils::GetVectorFromJson(Params, TEXT("location"));
        AIC->MoveToLocation(Location, AcceptanceRadius, bStopOnOverlap);

        TSharedPtr<FJsonObject> Result = MakeShared<FJsonObject>();
        Result->SetStringField(TEXT("status"), TEXT("Moving to location"));
        Result->SetStringField(TEXT("target"), Location.ToString());
        return Result;
    }

    return FEpicUnrealMCPCommonUtils::CreateErrorResponse(TEXT("Missing 'target_actor' or 'location' parameter"));
}

TSharedPtr<FJsonObject> FEpicUnrealMCPAICommands::HandleRunBehaviorTree(const TSharedPtr<FJsonObject>& Params)
{
    FString ActorName;
    if (!Params->TryGetStringField(TEXT("actor_name"), ActorName))
    {
        return FEpicUnrealMCPCommonUtils::CreateErrorResponse(TEXT("Missing 'actor_name' parameter"));
    }

    FString BTPath;
    if (!Params->TryGetStringField(TEXT("bt_path"), BTPath))
    {
        return FEpicUnrealMCPCommonUtils::CreateErrorResponse(TEXT("Missing 'bt_path' parameter"));
    }

    AActor* TargetActor = FEpicUnrealMCPCommonUtils::FindActorByName(ActorName);
    APawn* Pawn = Cast<APawn>(TargetActor);
    if (!Pawn)
    {
        return FEpicUnrealMCPCommonUtils::CreateErrorResponse(FString::Printf(TEXT("Actor not found or is not a Pawn: %s"), *ActorName));
    }

    AAIController* AIC = Cast<AAIController>(Pawn->GetController());
    if (!AIC)
    {
        // Try to find the AI controller if it's not possessed yet or if the actor itself is the controller
        AIC = Cast<AAIController>(TargetActor);
    }

    if (!AIC)
    {
        return FEpicUnrealMCPCommonUtils::CreateErrorResponse(FString::Printf(TEXT("Could not find AI Controller for %s"), *ActorName));
    }

    UBehaviorTree* BT = Cast<UBehaviorTree>(StaticLoadObject(UBehaviorTree::StaticClass(), nullptr, *BTPath));
    if (!BT)
    {
        return FEpicUnrealMCPCommonUtils::CreateErrorResponse(FString::Printf(TEXT("Failed to load Behavior Tree: %s"), *BTPath));
    }

    bool bSuccess = AIC->RunBehaviorTree(BT);

    TSharedPtr<FJsonObject> Result = MakeShared<FJsonObject>();
    Result->SetBoolField(TEXT("success"), bSuccess);
    Result->SetStringField(TEXT("message"), bSuccess ? TEXT("Behavior Tree started") : TEXT("Failed to start Behavior Tree"));
    return Result;
}

TSharedPtr<FJsonObject> FEpicUnrealMCPAICommands::HandleSetBlackboardValue(const TSharedPtr<FJsonObject>& Params)
{
    FString ActorName;
    if (!Params->TryGetStringField(TEXT("actor_name"), ActorName))
    {
        return FEpicUnrealMCPCommonUtils::CreateErrorResponse(TEXT("Missing 'actor_name' parameter"));
    }

    FString KeyName;
    if (!Params->TryGetStringField(TEXT("key_name"), KeyName))
    {
        return FEpicUnrealMCPCommonUtils::CreateErrorResponse(TEXT("Missing 'key_name' parameter"));
    }

    AActor* TargetActor = FEpicUnrealMCPCommonUtils::FindActorByName(ActorName);
    APawn* Pawn = Cast<APawn>(TargetActor);
    AAIController* AIC = nullptr;

    if (Pawn) AIC = Cast<AAIController>(Pawn->GetController());
    else AIC = Cast<AAIController>(TargetActor);

    if (!AIC || !AIC->GetBlackboardComponent())
    {
        return FEpicUnrealMCPCommonUtils::CreateErrorResponse(FString::Printf(TEXT("Actor %s has no Blackboard component"), *ActorName));
    }

    UBlackboardComponent* BB = AIC->GetBlackboardComponent();
    FName BlackboardKey(*KeyName);

    if (Params->HasField(TEXT("value_bool")))
    {
        BB->SetValueAsBool(BlackboardKey, Params->GetBoolField(TEXT("value_bool")));
    }
    else if (Params->HasField(TEXT("value_float")))
    {
        BB->SetValueAsFloat(BlackboardKey, Params->GetNumberField(TEXT("value_float")));
    }
    else if (Params->HasField(TEXT("value_int")))
    {
        BB->SetValueAsInt(BlackboardKey, (int32)Params->GetNumberField(TEXT("value_int")));
    }
    else if (Params->HasField(TEXT("value_string")))
    {
        BB->SetValueAsString(BlackboardKey, Params->GetStringField(TEXT("value_string")));
    }
    else if (Params->HasField(TEXT("value_vector")))
    {
        BB->SetValueAsVector(BlackboardKey, FEpicUnrealMCPCommonUtils::GetVectorFromJson(Params, TEXT("value_vector")));
    }
    else if (Params->HasField(TEXT("value_object")))
    {
        FString ObjectName = Params->GetStringField(TEXT("value_object"));
        AActor* Obj = FEpicUnrealMCPCommonUtils::FindActorByName(ObjectName);
        BB->SetValueAsObject(BlackboardKey, Obj);
    }
    else
    {
        return FEpicUnrealMCPCommonUtils::CreateErrorResponse(TEXT("No valid 'value_...' parameter provided"));
    }

    TSharedPtr<FJsonObject> Result = MakeShared<FJsonObject>();
    Result->SetBoolField(TEXT("success"), true);
    Result->SetStringField(TEXT("key"), KeyName);
    return Result;
}

TSharedPtr<FJsonObject> FEpicUnrealMCPAICommands::HandleGetPerceptionInfo(const TSharedPtr<FJsonObject>& Params)
{
    FString ActorName;
    if (!Params->TryGetStringField(TEXT("actor_name"), ActorName))
    {
        return FEpicUnrealMCPCommonUtils::CreateErrorResponse(TEXT("Missing 'actor_name' parameter"));
    }

    AActor* TargetActor = FEpicUnrealMCPCommonUtils::FindActorByName(ActorName);
    APawn* Pawn = Cast<APawn>(TargetActor);
    AAIController* AIC = nullptr;

    if (Pawn) AIC = Cast<AAIController>(Pawn->GetController());
    else AIC = Cast<AAIController>(TargetActor);

    if (!AIC || !AIC->GetAIPerceptionComponent())
    {
        return FEpicUnrealMCPCommonUtils::CreateErrorResponse(FString::Printf(TEXT("Actor %s has no AIPerception component"), *ActorName));
    }

    UAIPerceptionComponent* Perception = AIC->GetAIPerceptionComponent();
    TArray<AActor*> PerceivedActors;
    Perception->GetCurrentlyPerceivedActors(UAISense_Sight::StaticClass(), PerceivedActors);

    TArray<TSharedPtr<FJsonValue>> PerceivedList;
    for (AActor* Actor : PerceivedActors)
    {
        if (Actor)
        {
            TSharedPtr<FJsonObject> ActorObj = MakeShared<FJsonObject>();
            ActorObj->SetStringField(TEXT("name"), Actor->GetName());
            ActorObj->SetStringField(TEXT("class"), Actor->GetClass()->GetName());
            
            FAIStimulus Stimulus;
            // Note: In a real implementation we'd probably want more detailed stimulus data
            // but for now we just return the names of seen actors.
            
            PerceivedList.Add(MakeShared<FJsonValueObject>(ActorObj));
        }
    }

    TSharedPtr<FJsonObject> Result = MakeShared<FJsonObject>();
    Result->SetArrayField(TEXT("perceived_actors"), PerceivedList);
    Result->SetNumberField(TEXT("count"), PerceivedList.Num());
    return Result;
}

TSharedPtr<FJsonObject> FEpicUnrealMCPAICommands::HandleRegisterPerceptionSource(const TSharedPtr<FJsonObject>& Params)
{
    FString ActorName;
    if (!Params->TryGetStringField(TEXT("actor_name"), ActorName))
    {
        return FEpicUnrealMCPCommonUtils::CreateErrorResponse(TEXT("Missing 'actor_name' parameter"));
    }

    AActor* TargetActor = FEpicUnrealMCPCommonUtils::FindActorByName(ActorName);
    if (!TargetActor)
    {
        return FEpicUnrealMCPCommonUtils::CreateErrorResponse(FString::Printf(TEXT("Actor not found: %s"), *ActorName));
    }

    UAIPerceptionSystem::RegisterPerceptionStimuliSource(TargetActor->GetWorld(), UAISense_Sight::StaticClass(), TargetActor);

    TSharedPtr<FJsonObject> Result = MakeShared<FJsonObject>();
    Result->SetBoolField(TEXT("success"), true);
    Result->SetStringField(TEXT("message"), FString::Printf(TEXT("Registered %s as perception source"), *ActorName));
    return Result;
}

TSharedPtr<FJsonObject> FEpicUnrealMCPAICommands::HandleGetAIStatus(const TSharedPtr<FJsonObject>& Params)
{
    FString ActorName;
    if (!Params->TryGetStringField(TEXT("actor_name"), ActorName))
    {
        return FEpicUnrealMCPCommonUtils::CreateErrorResponse(TEXT("Missing 'actor_name' parameter"));
    }

    AActor* TargetActor = FEpicUnrealMCPCommonUtils::FindActorByName(ActorName);
    APawn* Pawn = Cast<APawn>(TargetActor);
    AAIController* AIC = nullptr;

    if (Pawn) AIC = Cast<AAIController>(Pawn->GetController());
    else AIC = Cast<AAIController>(TargetActor);

    if (!AIC)
    {
        return FEpicUnrealMCPCommonUtils::CreateErrorResponse(FString::Printf(TEXT("Could not find AI Controller for %s"), *ActorName));
    }

    TSharedPtr<FJsonObject> Result = MakeShared<FJsonObject>();
    Result->SetStringField(TEXT("actor"), ActorName);
    bool bIsMoving = (AIC->GetMoveStatus() != EPathFollowingStatus::Type::Idle);
    Result->SetBoolField(TEXT("is_moving"), bIsMoving);
    Result->SetStringField(TEXT("move_status"), TEXT("Unknown Status"));
    
    if (AIC->GetBlackboardComponent())
    {
        Result->SetBoolField(TEXT("has_blackboard"), true);
    }
    
    if (AIC->GetAIPerceptionComponent())
    {
        Result->SetBoolField(TEXT("has_perception"), true);
    }

    return Result;
}

TSharedPtr<FJsonObject> FEpicUnrealMCPAICommands::HandleStopAIMovement(const TSharedPtr<FJsonObject>& Params)
{
    FString ActorName;
    if (!Params->TryGetStringField(TEXT("actor_name"), ActorName))
    {
        return FEpicUnrealMCPCommonUtils::CreateErrorResponse(TEXT("Missing 'actor_name' parameter"));
    }

    AActor* TargetActor = FEpicUnrealMCPCommonUtils::FindActorByName(ActorName);
    APawn* Pawn = Cast<APawn>(TargetActor);
    AAIController* AIC = nullptr;

    if (Pawn) AIC = Cast<AAIController>(Pawn->GetController());
    else AIC = Cast<AAIController>(TargetActor);

    if (!AIC)
    {
        return FEpicUnrealMCPCommonUtils::CreateErrorResponse(FString::Printf(TEXT("Could not find AI Controller for %s"), *ActorName));
    }

    AIC->StopMovement();
    
    TSharedPtr<FJsonObject> Result = MakeShared<FJsonObject>();
    Result->SetBoolField(TEXT("success"), true);
    Result->SetStringField(TEXT("message"), TEXT("Movement stopped"));
    return Result;
}

TSharedPtr<FJsonObject> FEpicUnrealMCPAICommands::HandleGetRandomReachablePoint(const TSharedPtr<FJsonObject>& Params)
{
    FVector Origin(0, 0, 0);
    if (Params->HasField(TEXT("origin")))
    {
        Origin = FEpicUnrealMCPCommonUtils::GetVectorFromJson(Params, TEXT("origin"));
    }
    else if (Params->HasField(TEXT("actor_name")))
    {
        FString ActorName = Params->GetStringField(TEXT("actor_name"));
        AActor* Actor = FEpicUnrealMCPCommonUtils::FindActorByName(ActorName);
        if (Actor) Origin = Actor->GetActorLocation();
    }

    float Radius = 1000.0f;
    Params->TryGetNumberField(TEXT("radius"), Radius);

    // In UE 5.7, UNavigationSystemV1 is often retrieved via FNavigationSystem::GetCurrent
    // We'll try to use the most common interface
    UNavigationSystemV1* NavSys = FNavigationSystem::GetCurrent<UNavigationSystemV1>(GEditor->GetEditorWorldContext().World());
    if (!NavSys)
    {
        return FEpicUnrealMCPCommonUtils::CreateErrorResponse(TEXT("Navigation System not found"));
    }

    FNavLocation RandomPt;
    bool bFound = NavSys->GetRandomReachablePointInRadius(Origin, Radius, RandomPt);

    if (bFound)
    {
        TSharedPtr<FJsonObject> Result = MakeShared<FJsonObject>();
        Result->SetBoolField(TEXT("success"), true);
        FEpicUnrealMCPCommonUtils::AddVectorToJson(Result, TEXT("point"), RandomPt.Location);
        return Result;
    }

    return FEpicUnrealMCPCommonUtils::CreateErrorResponse(TEXT("Failed to find reachable point"));
}

TSharedPtr<FJsonObject> FEpicUnrealMCPAICommands::HandleRunEQSQuery(const TSharedPtr<FJsonObject>& Params)
{
    FString QueryPath;
    if (!Params->TryGetStringField(TEXT("query_path"), QueryPath))
    {
        return FEpicUnrealMCPCommonUtils::CreateErrorResponse(TEXT("Missing 'query_path' parameter"));
    }

    FString QuerierName;
    Params->TryGetStringField(TEXT("querier_name"), QuerierName);
    AActor* Querier = QuerierName.IsEmpty() ? nullptr : FEpicUnrealMCPCommonUtils::FindActorByName(QuerierName);

    UEnvQuery* Query = Cast<UEnvQuery>(StaticLoadObject(UEnvQuery::StaticClass(), nullptr, *QueryPath));
    if (!Query)
    {
        return FEpicUnrealMCPCommonUtils::CreateErrorResponse(FString::Printf(TEXT("Failed to load EQS Query: %s"), *QueryPath));
    }

    FEnvQueryRequest QueryRequest(Query, Querier);
    
    // In 5.7, we use the newer result handling via InstantQuery for synchronous execution
    UEnvQueryManager* EnvQueryManager = UEnvQueryManager::GetCurrent(GEditor->GetEditorWorldContext().World());
    if (!EnvQueryManager)
    {
        return FEpicUnrealMCPCommonUtils::CreateErrorResponse(TEXT("Failed to get EnvQueryManager"));
    }

    TSharedPtr<FEnvQueryResult> QueryResult = EnvQueryManager->RunInstantQuery(QueryRequest, EEnvQueryRunMode::AllMatching);
    
    TArray<AActor*> ResultActors;
    if (QueryResult.IsValid())
    {
        QueryResult->GetAllAsActors(ResultActors);
    }

    TArray<TSharedPtr<FJsonValue>> ActorList;
    for (AActor* Actor : ResultActors)
    {
        if (Actor)
        {
            TSharedPtr<FJsonObject> ActorObj = MakeShared<FJsonObject>();
            ActorObj->SetStringField(TEXT("name"), Actor->GetName());
            ActorList.Add(MakeShared<FJsonValueObject>(ActorObj));
        }
    }

    TSharedPtr<FJsonObject> Result = MakeShared<FJsonObject>();
    Result->SetBoolField(TEXT("success"), true);
    Result->SetArrayField(TEXT("items"), ActorList);
    Result->SetNumberField(TEXT("count"), ActorList.Num());
    return Result;
}
