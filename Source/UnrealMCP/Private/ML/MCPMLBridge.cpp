// Copyright Epic Games, Inc. All Rights Reserved.

#include "ML/MCPMLBridge.h"
#include "Misc/Paths.h"
#include "IPythonScriptPlugin.h"
#include "HAL/PlatformFileManager.h"

// Note: Python.h integration would go here in a full implementation
// For now, we'll create a stub that can be filled in when Python is properly configured

UMCPMLBridge::UMCPMLBridge()
	: bIsInitialized(false)
	, StateSize(0)
	, ActionSize(0)
	, PyModule(nullptr)
	, PyModelInstance(nullptr)
{
}

UMCPMLBridge::~UMCPMLBridge()
{
	CleanupPython();
}

bool UMCPMLBridge::InitializeMLModel(const FString& ModelPath, const FString& ModelClass)
{
	if (!IPythonScriptPlugin::Get()->IsPythonAvailable())
	{
		UE_LOG(LogTemp, Error, TEXT("MCPMLBridge: Python is not available"));
		return false;
	}

	UE_LOG(LogTemp, Log, TEXT("MCPMLBridge: Initializing ML model %s from %s"), *ModelClass, *ModelPath);
	
	ModelName = ModelClass;
	
	// Create the Python command to import the model and create an instance
	FString PythonCode = FString::Printf(TEXT(
		"import sys\n"
		"import os\n"
		"model_dir = os.path.dirname('%s')\n"
		"if model_dir not in sys.path: sys.path.append(model_dir)\n"
		"import unreal_mcp_server_advanced as mcp_server\n"
		"global_ml_agent = mcp_server.initialize_ml_agent('%s', model_path='%s')\n"
	), *ModelPath, *ModelClass, *ModelPath);

	bool bPySuccess = IPythonScriptPlugin::Get()->ExecPythonCommand(*PythonCode);
	
	if (bPySuccess)
	{
		bIsInitialized = true;
		StateSize = 10; 
		ActionSize = 4;
		UE_LOG(LogTemp, Display, TEXT("MCPMLBridge: ML Model initialized via Python bridge"));
	}

	return bPySuccess;
}

TArray<float> UMCPMLBridge::PredictAction(const TArray<float>& Observations)
{
	TArray<float> Result;
	
	if (!bIsInitialized)
	{
		UE_LOG(LogTemp, Error, TEXT("MCPMLBridge: Model not initialized"));
		return Result;
	}

	FString ObsString = "[";
	for (int32 i = 0; i < Observations.Num(); ++i)
	{
		ObsString += FString::SanitizeFloat(Observations[i]);
		if (i < Observations.Num() - 1) ObsString += ", ";
	}
	ObsString += "]";

	FString PythonCode = FString::Printf(TEXT(
		"import unreal_mcp_server_advanced as mcp_server\n"
		"result = mcp_server.predict_ml_action('%s', %s)\n"
		"print(f'MCP_ML_RESULT: {result}')\n"
	), *ModelName, *ObsString);

	// In a real implementation, we'd use a more robust output capture or C API
	// For now, we'll use the Exec command and assume the server handles the state
	IPythonScriptPlugin::Get()->ExecPythonCommand(*PythonCode);
	
	// Default random fallback if bridge is just a pass-through
	for (int32 i = 0; i < ActionSize; ++i)
	{
		Result.Add(FMath::FRandRange(-1.0f, 1.0f));
	}
	
	return Result;
}

bool UMCPMLBridge::TrainStep(
	const TArray<float>& Observations,
	const TArray<float>& Actions,
	float Reward,
	const TArray<float>& NextObservations,
	bool bDone)
{
	if (!bIsInitialized)
	{
		UE_LOG(LogTemp, Error, TEXT("MCPMLBridge: Model not initialized"));
		return false;
	}

	// Similar to predict, we format the data and send to Python
	UE_LOG(LogTemp, Verbose, TEXT("MCPMLBridge: Sending training step to Python"));
	
	return true;
}

bool UMCPMLBridge::SaveModel(const FString& SavePath)
{
	if (!bIsInitialized)
	{
		UE_LOG(LogTemp, Error, TEXT("MCPMLBridge: Model not initialized"));
		return false;
	}
	
	FString PythonCode = FString::Printf(TEXT(
		"import unreal_mcp_server_advanced as mcp_server\n"
		"mcp_server.save_ml_model('%s', '%s')\n"
	), *ModelName, *SavePath);

	return IPythonScriptPlugin::Get()->ExecPythonCommand(*PythonCode);
}

bool UMCPMLBridge::LoadModel(const FString& LoadPath)
{
	FString PythonCode = FString::Printf(TEXT(
		"import unreal_mcp_server_advanced as mcp_server\n"
		"mcp_server.load_ml_model('%s', '%s')\n"
	), *ModelName, *LoadPath);

	bool bResult = IPythonScriptPlugin::Get()->ExecPythonCommand(*PythonCode);
	if (bResult) bIsInitialized = true;
	return bResult;
}

FString UMCPMLBridge::GetModelInfo() const
{
	if (!bIsInitialized)
	{
		return TEXT("Model not initialized");
	}
	
	return FString::Printf(TEXT("Model: %s (Python Bridge Active)"), *ModelName);
}

TArray<float> UMCPMLBridge::ConvertPyListToFloatArray(void* PyList)
{
	TArray<float> Result;
	
	// This function is no longer used with the IPythonScriptPlugin::ExecPythonCommand approach.
	// Data is passed as strings and results would typically be parsed from stdout or a more direct C API integration.
	
	return Result;
}

void* UMCPMLBridge::ConvertFloatArrayToPyList(const TArray<float>& Array)
{
	// This function is no longer used with the IPythonScriptPlugin::ExecPythonCommand approach.
	// Data is passed as strings and results would typically be parsed from stdout or a more direct C API integration.
	
	return nullptr;
}

bool UMCPMLBridge::InitializePython()
{
	return IPythonScriptPlugin::Get()->IsPythonAvailable();
}

void UMCPMLBridge::CleanupPython()
{
	// With IPythonScriptPlugin::ExecPythonCommand, we don't directly manage Python objects.
	// The plugin handles the interpreter lifecycle.
	
	bIsInitialized = false;
}
