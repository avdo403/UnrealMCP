#pragma once

#include "CoreMinimal.h"
#include "Json.h"

/**
 * Handler class for AI-related MCP commands
 */
class FEpicUnrealMCPAICommands
{
public:
    FEpicUnrealMCPAICommands();

    /**
     * Handle AI-related commands
     * @param CommandType The name of the command
     * @param Params JSON object containing command parameters
     * @return JSON response object
     */
    TSharedPtr<FJsonObject> HandleCommand(const FString& CommandType, const TSharedPtr<FJsonObject>& Params);

private:
    /**
     * Move an AI pawn to a specific location or actor
     */
    TSharedPtr<FJsonObject> HandleAIMoveTo(const TSharedPtr<FJsonObject>& Params);

    /**
     * Run a behavior tree on an AI controller
     */
    TSharedPtr<FJsonObject> HandleRunBehaviorTree(const TSharedPtr<FJsonObject>& Params);

    /**
     * Set a value in a chalkboard
     */
    TSharedPtr<FJsonObject> HandleSetBlackboardValue(const TSharedPtr<FJsonObject>& Params);

    /**
     * Get information about perceived actors
     */
    TSharedPtr<FJsonObject> HandleGetPerceptionInfo(const TSharedPtr<FJsonObject>& Params);

    /**
     * Register an actor as a perception stimulus source
     */
    TSharedPtr<FJsonObject> HandleRegisterPerceptionSource(const TSharedPtr<FJsonObject>& Params);

    /**
     * Get the current status of an AI (is it moving? what is it doing?)
     */
    TSharedPtr<FJsonObject> HandleGetAIStatus(const TSharedPtr<FJsonObject>& Params);

    /**
     * Stop current AI movement
     */
    TSharedPtr<FJsonObject> HandleStopAIMovement(const TSharedPtr<FJsonObject>& Params);

    /**
     * Get a random reachable point on the navmesh
     */
    TSharedPtr<FJsonObject> HandleGetRandomReachablePoint(const TSharedPtr<FJsonObject>& Params);

    /**
     * Execute an EQS (Environment Query System) query
     */
    TSharedPtr<FJsonObject> HandleRunEQSQuery(const TSharedPtr<FJsonObject>& Params);
};
