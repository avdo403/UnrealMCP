// Copyright Epic Games, Inc. All Rights Reserved.

#pragma once

#include "CoreMinimal.h"
#include "GameplayTask.h"
#include "AIController.h"
#include "GameplayTaskOwnerInterface.h"
#include "MCPGameplayTask_AIAction.generated.h"

/**
 * Base class for MCP-controlled AI tasks using GameplayTask framework
 * 
 * This allows async AI operations with proper lifecycle management.
 * Integrates with Behavior Trees, StateTree, and direct AI control.
 * 
 * Example Usage:
 *   auto Task = UMCPGameplayTask_AIAction::ExecuteAIAction(
 *       MyAIController, 
 *       "MoveToTarget", 
 *       {{"TargetLocation", "100,200,300"}}
 *   );
 *   Task->OnCompleted.AddDynamic(this, &AMyClass::OnActionComplete);
 */
UCLASS()
class UNREALMCP_API UMCPGameplayTask_AIAction : public UGameplayTask
{
	GENERATED_BODY()

public:
	UMCPGameplayTask_AIAction(const FObjectInitializer& ObjectInitializer);

	/**
	 * Create and execute an AI action task
	 * @param Controller The AI controller to execute the action on
	 * @param ActionName Name of the action to execute
	 * @param Parameters Key-value parameters for the action
	 * @return The created task instance
	 */
	UFUNCTION(BlueprintCallable, Category = "MCP|AI", meta = (BlueprintInternalUseOnly = "TRUE"))
	static UMCPGameplayTask_AIAction* ExecuteAIAction(
		AAIController* Controller,
		FName ActionName,
		const TMap<FString, FString>& Parameters
	);

	/** Called when task completes successfully */
	DECLARE_DYNAMIC_MULTICAST_DELEGATE(FMCPAIActionComplete);
	UPROPERTY(BlueprintAssignable)
	FMCPAIActionComplete OnCompleted;

	/** Called when task fails */
	DECLARE_DYNAMIC_MULTICAST_DELEGATE_OneParam(FMCPAIActionFailed, FString, Reason);
	UPROPERTY(BlueprintAssignable)
	FMCPAIActionFailed OnFailed;

	/** Get the action name */
	UFUNCTION(BlueprintPure, Category = "MCP|AI")
	FName GetActionName() const { return ActionName; }

	/** Get action parameters */
	UFUNCTION(BlueprintPure, Category = "MCP|AI")
	const TMap<FString, FString>& GetParameters() const { return ActionParameters; }

protected:
	virtual void Activate() override;
	virtual void OnDestroy(bool bInOwnerFinished) override;
	virtual void TickTask(float DeltaTime) override;

	/** Execute the actual AI action logic */
	virtual void ExecuteAction();

	/** Complete the task successfully */
	UFUNCTION()
	void CompleteTask();

	/** Fail the task with a reason */
	UFUNCTION()
	void FailTask(const FString& Reason);

private:
	UPROPERTY()
	TObjectPtr<AAIController> AIController;

	FName ActionName;
	TMap<FString, FString> ActionParameters;

	/** Track if task is currently executing */
	bool bIsExecuting;
};
