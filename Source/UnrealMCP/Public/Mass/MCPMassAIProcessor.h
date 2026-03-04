// Copyright Epic Games, Inc. All Rights Reserved.

#pragma once

#include "CoreMinimal.h"
#include "MassProcessor.h"
#include "MCPMassFragments.h"
#include "MCPMassAIProcessor.generated.h"

/**
 * Processor to update MCP AI state for Mass entities
 * Handles AI logic for thousands of entities efficiently
 * 
 * Note: UE 5.7 changed Mass API - ConfigureQueries is now final
 */
UCLASS()
class UNREALMCP_API UMCPMassAIProcessor : public UMassProcessor
{
	GENERATED_BODY()

public:
	UMCPMassAIProcessor();

protected:
	virtual void InitializeInternal(UObject& Owner, const TSharedRef<FMassEntityManager>& EntityManager) override;
	virtual void Execute(FMassEntityManager& EntityManager, FMassExecutionContext& Context) override;

private:
	FMassEntityQuery EntityQuery;
};
