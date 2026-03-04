#pragma once

#include "CoreMinimal.h"
#include "Dom/JsonObject.h"

/**
 * Handlers for StateTree related MCP commands
 */
class FEpicUnrealMCPStateTreeCommands
{
public:
    FEpicUnrealMCPStateTreeCommands();

    /** Processes a StateTree command */
    TSharedPtr<FJsonObject> HandleCommand(const FString& CommandType, const TSharedPtr<FJsonObject>& Params);

private:
    /** Runs a StateTree on an actor */
    TSharedPtr<FJsonObject> HandleRunStateTree(const TSharedPtr<FJsonObject>& Params);

    /** Sends an event to a running StateTree */
    TSharedPtr<FJsonObject> HandleSendStateTreeEvent(const TSharedPtr<FJsonObject>& Params);

    /** Stops a running StateTree */
    TSharedPtr<FJsonObject> HandleStopStateTree(const TSharedPtr<FJsonObject>& Params);
};
