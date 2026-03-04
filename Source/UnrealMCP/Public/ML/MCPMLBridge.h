// Copyright Epic Games, Inc. All Rights Reserved.

#pragma once

#include "CoreMinimal.h"
#include "UObject/NoExportTypes.h"
#include "MCPMLBridge.generated.h"

/**
 * Bridge between Unreal C++ and Python ML models
 * Enables runtime ML inference for AI agents
 * 
 * Example Usage:
 *   UMCPMLBridge* MLBridge = NewObject<UMCPMLBridge>();
 *   MLBridge->InitializeMLModel("models/agent.pth", "MCPRLAgent");
 *   TArray<float> Actions = MLBridge->PredictAction(Observations);
 */
UCLASS(BlueprintType)
class UNREALMCP_API UMCPMLBridge : public UObject
{
	GENERATED_BODY()

public:
	UMCPMLBridge();
	virtual ~UMCPMLBridge();

	/** Initialize Python ML model */
	UFUNCTION(BlueprintCallable, Category = "MCP|ML")
	bool InitializeMLModel(const FString& ModelPath, const FString& ModelClass);

	/** Get prediction from ML model */
	UFUNCTION(BlueprintCallable, Category = "MCP|ML")
	TArray<float> PredictAction(const TArray<float>& Observations);

	/** Train model with new data (if supported) */
	UFUNCTION(BlueprintCallable, Category = "MCP|ML")
	bool TrainStep(
		const TArray<float>& Observations,
		const TArray<float>& Actions,
		float Reward,
		const TArray<float>& NextObservations,
		bool bDone
	);

	/** Save trained model */
	UFUNCTION(BlueprintCallable, Category = "MCP|ML")
	bool SaveModel(const FString& SavePath);

	/** Load trained model */
	UFUNCTION(BlueprintCallable, Category = "MCP|ML")
	bool LoadModel(const FString& LoadPath);

	/** Check if model is initialized */
	UFUNCTION(BlueprintPure, Category = "MCP|ML")
	bool IsModelInitialized() const { return bIsInitialized; }

	/** Get model info */
	UFUNCTION(BlueprintPure, Category = "MCP|ML")
	FString GetModelInfo() const;

private:
	/** Whether the model is initialized */
	bool bIsInitialized;

	/** Model name for logging */
	FString ModelName;

	/** State size */
	int32 StateSize;

	/** Action size */
	int32 ActionSize;

	/** Python module and model instance (stored as void* for cross-platform compatibility) */
	void* PyModule;
	void* PyModelInstance;

	/** Helper functions for Python interop */
	TArray<float> ConvertPyListToFloatArray(void* PyList);
	void* ConvertFloatArrayToPyList(const TArray<float>& Array);
	
	/** Initialize Python interpreter if needed */
	bool InitializePython();
	
	/** Cleanup Python resources */
	void CleanupPython();
};
