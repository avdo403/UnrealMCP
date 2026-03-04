#pragma once

#include "CoreMinimal.h"
#include "Dom/JsonObject.h"

/**
 * Handlers for Mass Entity related MCP commands
 */
class FEpicUnrealMCPMassCommands
{
public:
    FEpicUnrealMCPMassCommands();

    /** Processes a Mass command */
    TSharedPtr<FJsonObject> HandleCommand(const FString& CommandType, const TSharedPtr<FJsonObject>& Params);

private:
    /** Spawns a crowd of Mass entities */
    TSharedPtr<FJsonObject> HandleSpawnMassCrowd(const TSharedPtr<FJsonObject>& Params);

    /** Updates properties of Mass entities */
    TSharedPtr<FJsonObject> HandleUpdateMassEntities(const TSharedPtr<FJsonObject>& Params);
};
