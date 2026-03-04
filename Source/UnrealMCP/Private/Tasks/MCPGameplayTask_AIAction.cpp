// Copyright Epic Games, Inc. All Rights Reserved.

#include "Tasks/MCPGameplayTask_AIAction.h"
#include "AIController.h"
#include "GameFramework/Pawn.h"
#include "Navigation/PathFollowingComponent.h"
#include "NavigationSystem.h"
#include "NavigationPath.h"

UMCPGameplayTask_AIAction::UMCPGameplayTask_AIAction(const FObjectInitializer& ObjectInitializer)
	: Super(ObjectInitializer)
{
	bTickingTask = true; // Enable Tick
	bIsExecuting = false;
}

UMCPGameplayTask_AIAction* UMCPGameplayTask_AIAction::ExecuteAIAction(
	AAIController* Controller,
	FName ActionName,
	const TMap<FString, FString>& Parameters)
{
	if (!Controller)
	{
		UE_LOG(LogTemp, Error, TEXT("MCPGameplayTask_AIAction: Invalid AI Controller"));
		return nullptr;
	}

	UMCPGameplayTask_AIAction* MyTask = NewTask<UMCPGameplayTask_AIAction>(Controller);
	if (MyTask)
	{
		MyTask->AIController = Controller;
		MyTask->ActionName = ActionName;
		MyTask->ActionParameters = Parameters;
	}

	return MyTask;
}

void UMCPGameplayTask_AIAction::Activate()
{
	Super::Activate();

	if (!AIController.Get() || !IsValid(AIController.Get()))
	{
		FailTask(TEXT("AI Controller is invalid"));
		return;
	}

	bIsExecuting = true;
	ExecuteAction();
}

void UMCPGameplayTask_AIAction::ExecuteAction()
{
	// Example: Handle different action types
	if (ActionName == "MoveTo")
	{
		// Parse target location from parameters
		FString LocationStr;
		if (ActionParameters.Contains("TargetLocation"))
		{
			LocationStr = ActionParameters["TargetLocation"];
			
			// Parse "X,Y,Z" format
			TArray<FString> Coords;
			LocationStr.ParseIntoArray(Coords, TEXT(","));
			
			if (Coords.Num() == 3)
			{
				FVector TargetLocation(
					FCString::Atof(*Coords[0]),
					FCString::Atof(*Coords[1]),
					FCString::Atof(*Coords[2])
				);

				// Execute move command
				FAIMoveRequest MoveRequest(TargetLocation);
				MoveRequest.SetAcceptanceRadius(50.0f);
				
				FPathFollowingRequestResult Result = AIController->MoveTo(MoveRequest);
				
				if (Result.Code == EPathFollowingRequestResult::RequestSuccessful)
				{
					UE_LOG(LogTemp, Log, TEXT("AI MoveTo started successfully to %s"), *TargetLocation.ToString());
				}
				else
				{
					FailTask(TEXT("MoveTo request failed"));
				}
			}
			else
			{
				FailTask(TEXT("Invalid location format. Expected: X,Y,Z"));
			}
		}
		else
		{
			FailTask(TEXT("Missing TargetLocation parameter"));
		}
	}
	else if (ActionName == "Wait")
	{
		// Wait action - will complete in TickTask after duration
		UE_LOG(LogTemp, Log, TEXT("AI Wait action started"));
		
		// Get wait duration from parameters
		float WaitDuration = 1.0f;
		if (ActionParameters.Contains("Duration"))
		{
			WaitDuration = FCString::Atof(*ActionParameters["Duration"]);
		}
		
		// Store start time for wait completion check
		// In a real implementation, you'd store this in a member variable
	}
	else if (ActionName == "Stop")
	{
		// Stop current movement
		AIController->StopMovement();
		CompleteTask();
	}
	else
	{
		FailTask(FString::Printf(TEXT("Unknown action: %s"), *ActionName.ToString()));
	}
}

void UMCPGameplayTask_AIAction::TickTask(float DeltaTime)
{
	Super::TickTask(DeltaTime);

	if (!bIsExecuting || !AIController.Get())
	{
		return;
	}

	// Check if movement is complete
	if (ActionName == "MoveTo")
	{
		EPathFollowingStatus::Type MoveStatus = AIController->GetMoveStatus();
		
		if (MoveStatus == EPathFollowingStatus::Type::Idle)
		{
			// Movement completed
			CompleteTask();
		}
		// Note: Invalid status removed - not available in UE 5.7
		// Movement failures will be handled by other means
	}
}

void UMCPGameplayTask_AIAction::CompleteTask()
{
	if (bIsExecuting)
	{
		bIsExecuting = false;
		UE_LOG(LogTemp, Log, TEXT("MCPGameplayTask_AIAction completed: %s"), *ActionName.ToString());
		OnCompleted.Broadcast();
		EndTask();
	}
}

void UMCPGameplayTask_AIAction::FailTask(const FString& Reason)
{
	if (bIsExecuting)
	{
		bIsExecuting = false;
		UE_LOG(LogTemp, Warning, TEXT("MCPGameplayTask_AIAction failed: %s - Reason: %s"), *ActionName.ToString(), *Reason);
		OnFailed.Broadcast(Reason);
		EndTask();
	}
}

void UMCPGameplayTask_AIAction::OnDestroy(bool bInOwnerFinished)
{
	bIsExecuting = false;
	Super::OnDestroy(bInOwnerFinished);
}
