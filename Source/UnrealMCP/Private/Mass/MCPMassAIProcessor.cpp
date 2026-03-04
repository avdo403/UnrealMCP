// Copyright Epic Games, Inc. All Rights Reserved.

#include "Mass/MCPMassAIProcessor.h"
#include "MassCommonFragments.h"
// Note: MassMovementFragments.h and MassNavigationFragments.h may not exist in all UE versions
// Using basic fragments only
#include "MassExecutionContext.h"

UMCPMassAIProcessor::UMCPMassAIProcessor()
{
	ExecutionOrder.ExecuteInGroup = FName("Behavior");
}

void UMCPMassAIProcessor::InitializeInternal(UObject& Owner, const TSharedRef<FMassEntityManager>& EntityManager)
{
	Super::InitializeInternal(Owner, EntityManager);
	
	EntityQuery.AddRequirement<FMCPAIStateFragment>(EMassFragmentAccess::ReadWrite);
	EntityQuery.AddRequirement<FTransformFragment>(EMassFragmentAccess::ReadOnly);
	EntityQuery.AddTagRequirement<FMCPControlledTag>(EMassFragmentPresence::All);
}

void UMCPMassAIProcessor::Execute(
	FMassEntityManager& EntityManager, 
	FMassExecutionContext& Context)
{
	EntityQuery.ForEachEntityChunk(Context, [this](FMassExecutionContext& Context)
	{
		const TArrayView<FMCPAIStateFragment> AIStateList = Context.GetMutableFragmentView<FMCPAIStateFragment>();
		const TConstArrayView<FTransformFragment> TransformList = Context.GetFragmentView<FTransformFragment>();
		const float DeltaTime = Context.GetDeltaTimeSeconds();

			for (int32 i = 0; i < Context.GetNumEntities(); ++i)
			{
				FMCPAIStateFragment& AIState = AIStateList[i];
				const FTransformFragment& Transform = TransformList[i];

				AIState.TimeSinceStateChange += DeltaTime;

				// Simple AI logic based on state
				if (AIState.CurrentState == "Moving")
				{
					// Calculate direction to target
					FVector CurrentLocation = Transform.GetTransform().GetLocation();
					FVector Direction = AIState.TargetLocation - CurrentLocation;
					const float Distance = Direction.Size();

					if (Distance <= 50.0f) // Acceptance radius
					{
						// Reached target
						AIState.CurrentState = "Idle";
						AIState.TimeSinceStateChange = 0.0f;
						
						UE_LOG(LogTemp, Verbose, TEXT("Mass Entity reached target"));
					}
				}
				else if (AIState.CurrentState == "Idle")
				{
					if (AIState.TimeSinceStateChange > 5.0f)
					{
						// Random behavior could go here
					}
				}
				else if (AIState.CurrentState == "Patrolling")
				{
					FVector CurrentLocation = Transform.GetTransform().GetLocation();
					FVector Direction = AIState.TargetLocation - CurrentLocation;
					const float Distance = Direction.Size();

					if (Distance <= 50.0f)
					{
						AIState.CurrentState = "Idle";
						AIState.TimeSinceStateChange = 0.0f;
					}
				}
			}
		}
	);
}
