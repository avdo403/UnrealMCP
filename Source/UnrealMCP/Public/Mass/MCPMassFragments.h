// Copyright Epic Games, Inc. All Rights Reserved.

#pragma once

#include "CoreMinimal.h"
#include "MassEntityTypes.h"
#include "MCPMassFragments.generated.h"

/**
 * Fragment to store MCP-specific AI state
 * Used by Mass Entity System for efficient AI processing
 */
USTRUCT()
struct UNREALMCP_API FMCPAIStateFragment : public FMassFragment
{
	GENERATED_BODY()

	/** Current AI state (Idle, Moving, Attacking, etc.) */
	UPROPERTY()
	FName CurrentState = "Idle";

	/** Target entity (if any) */
	UPROPERTY()
	FMassEntityHandle TargetEntity;

	/** Target location */
	UPROPERTY()
	FVector TargetLocation = FVector::ZeroVector;

	/** AI aggression level (0-1) */
	UPROPERTY()
	float AggressionLevel = 0.5f;

	/** Time since last state change */
	UPROPERTY()
	float TimeSinceStateChange = 0.0f;

	/** Movement speed */
	UPROPERTY()
	float MovementSpeed = 300.0f;
};

/**
 * Fragment for ML-controlled agents
 * Stores machine learning state and observations
 */
USTRUCT()
struct UNREALMCP_API FMCPMLAgentFragment : public FMassFragment
{
	GENERATED_BODY()

	/** ML model name */
	UPROPERTY()
	FName ModelName;

	/** Last observation vector */
	UPROPERTY()
	TArray<float> LastObservations;

	/** Last action taken */
	UPROPERTY()
	TArray<float> LastActions;

	/** Cumulative reward */
	UPROPERTY()
	float CumulativeReward = 0.0f;

	/** Episode step count */
	UPROPERTY()
	int32 EpisodeSteps = 0;

	/** Whether this agent is in training mode */
	UPROPERTY()
	bool bIsTraining = false;
};

/**
 * Fragment for MCP command queue
 * Stores pending commands from MCP server
 */
USTRUCT()
struct UNREALMCP_API FMCPCommandQueueFragment : public FMassFragment
{
	GENERATED_BODY()

	/** Queue of pending commands */
	TArray<FString> PendingCommands;

	/** Command parameters */
	TMap<FString, FString> CommandParameters;
};

/**
 * Tag to identify MCP-controlled entities
 */
USTRUCT()
struct UNREALMCP_API FMCPControlledTag : public FMassTag
{
	GENERATED_BODY()
};

/**
 * Tag for entities using ML
 */
USTRUCT()
struct UNREALMCP_API FMCPMLControlledTag : public FMassTag
{
	GENERATED_BODY()
};

/**
 * Tag for entities in idle state
 */
USTRUCT()
struct UNREALMCP_API FMCPIdleTag : public FMassTag
{
	GENERATED_BODY()
};

/**
 * Tag for entities currently moving
 */
USTRUCT()
struct UNREALMCP_API FMCPMovingTag : public FMassTag
{
	GENERATED_BODY()
};
