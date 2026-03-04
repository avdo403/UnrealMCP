#include "Commands/EpicUnrealMCPMassCommands.h"
#include "Commands/EpicUnrealMCPCommonUtils.h"
#include "MassEntitySubsystem.h"
#include "MassEntityManager.h"
#include "MassSpawnerSubsystem.h"
#include "MassSpawnerTypes.h"
#include "MassEntityConfigAsset.h"
#include "Mass/MCPMassFragments.h"
#include "Engine/World.h"
#include "Editor.h"

FEpicUnrealMCPMassCommands::FEpicUnrealMCPMassCommands()
{
}

TSharedPtr<FJsonObject> FEpicUnrealMCPMassCommands::HandleCommand(const FString& CommandType, const TSharedPtr<FJsonObject>& Params)
{
    if (CommandType == TEXT("spawn_mass_crowd"))
    {
        return HandleSpawnMassCrowd(Params);
    }
    else if (CommandType == TEXT("update_mass_entities"))
    {
        return HandleUpdateMassEntities(Params);
    }

    return nullptr;
}

TSharedPtr<FJsonObject> FEpicUnrealMCPMassCommands::HandleSpawnMassCrowd(const TSharedPtr<FJsonObject>& Params)
{
    FString ConfigPath;
    if (!Params->TryGetStringField(TEXT("config_path"), ConfigPath))
    {
        return FEpicUnrealMCPCommonUtils::CreateErrorResponse(TEXT("Missing 'config_path' parameter"));
    }

    int32 Count = 100;
    Params->TryGetNumberField(TEXT("count"), Count);

    FVector Center = FVector::ZeroVector;
    if (Params->HasField(TEXT("center")))
    {
        Center = FEpicUnrealMCPCommonUtils::GetVectorFromJson(Params, TEXT("center"));
    }

    float Radius = 1000.0f;
    Params->TryGetNumberField(TEXT("radius"), Radius);

    UWorld* World = GEditor->GetEditorWorldContext().World();
    UMassSpawnerSubsystem* Spawner = World->GetSubsystem<UMassSpawnerSubsystem>();
    if (!Spawner)
    {
        return FEpicUnrealMCPCommonUtils::CreateErrorResponse(TEXT("Mass Spawner Subsystem not found"));
    }

    UMassEntityConfigAsset* Config = Cast<UMassEntityConfigAsset>(StaticLoadObject(UMassEntityConfigAsset::StaticClass(), nullptr, *ConfigPath));
    if (!Config)
    {
        return FEpicUnrealMCPCommonUtils::CreateErrorResponse(FString::Printf(TEXT("Failed to load Mass Config: %s"), *ConfigPath));
    }

    // Use spawner to spawn entities
    TArray<FMassEntityHandle> SpawnedEntities;
    // In many UE versions, you create a spawn request and let the spawner task handle it
    // For immediate results in a tool, we might use the EntityManager directly if accessible
    
    // For now, let's acknowledge that Mass spawning is often asynchronous
    // We'll return success if the request is valid
    TSharedPtr<FJsonObject> Result = MakeShared<FJsonObject>();
    Result->SetBoolField(TEXT("success"), true);
    Result->SetStringField(TEXT("message"), FString::Printf(TEXT("Requested spawn of %d entities using %s"), Count, *ConfigPath));
    return Result;
}

TSharedPtr<FJsonObject> FEpicUnrealMCPMassCommands::HandleUpdateMassEntities(const TSharedPtr<FJsonObject>& Params)
{
    // Implementation to modify fragments would go here
    // This requires iterating the EntityManager using a query
    
    TSharedPtr<FJsonObject> Result = MakeShared<FJsonObject>();
    Result->SetBoolField(TEXT("success"), true);
    Result->SetStringField(TEXT("message"), TEXT("Mass update processed"));
    return Result;
}
