#include "Commands/BlueprintGraph/BPConnector.h"
#include "Commands/EpicUnrealMCPCommonUtils.h"
#include "Engine/Blueprint.h"
#include "K2Node.h"
#include "EdGraph/EdGraph.h"
#include "EdGraph/EdGraphPin.h"
#include "EdGraphSchema_K2.h"
#include "Kismet2/KismetEditorUtilities.h"
#include "EditorAssetLibrary.h"

TSharedPtr<FJsonObject> FBPConnector::ConnectNodes(const TSharedPtr<FJsonObject>& Params)
{
    TSharedPtr<FJsonObject> Result = MakeShared<FJsonObject>();

    // Extraire paramètres
    FString BlueprintName = Params->GetStringField(TEXT("blueprint_name"));
    FString SourceNodeId = Params->GetStringField(TEXT("source_node_id"));
    FString SourcePinName = Params->GetStringField(TEXT("source_pin_name"));
    FString TargetNodeId = Params->GetStringField(TEXT("target_node_id"));
    FString TargetPinName = Params->GetStringField(TEXT("target_pin_name"));

    FString FunctionName;
    Params->TryGetStringField(TEXT("function_name"), FunctionName);

    // Charger Blueprint - use central utility
    UBlueprint* Blueprint = FEpicUnrealMCPCommonUtils::FindBlueprint(BlueprintName);

    if (!Blueprint)
    {
        Result->SetBoolField("success", false);
        Result->SetStringField("error", "Blueprint not found");
        return Result;
    }

    // Get graph
    UEdGraph* Graph = nullptr;

    if (!FunctionName.IsEmpty())
    {
        // Strategy 1: Try exact name match with GetFName()
        for (UEdGraph* FuncGraph : Blueprint->FunctionGraphs)
        {
            if (FuncGraph && (FuncGraph->GetFName().ToString() == FunctionName ||
                              (FuncGraph->GetOuter() && FuncGraph->GetOuter()->GetFName().ToString() == FunctionName)))
            {
                Graph = FuncGraph;
                break;
            }
        }

        // Strategy 2: Fallback - partial match for auto-generated names
        if (!Graph)
        {
            for (UEdGraph* FuncGraph : Blueprint->FunctionGraphs)
            {
                if (FuncGraph && FuncGraph->GetFName().ToString().Contains(FunctionName))
                {
                    Graph = FuncGraph;
                    break;
                }
            }
        }

        if (!Graph)
        {
            Result->SetBoolField("success", false);
            Result->SetStringField("error", FString::Printf(TEXT("Function graph not found: %s"), *FunctionName));
            return Result;
        }
    }
    else
    {
        // Use event graph if no function specified
        if (Blueprint->UbergraphPages.Num() == 0)
        {
            Result->SetBoolField("success", false);
            Result->SetStringField("error", "Blueprint has no event graph");
            return Result;
        }

        Graph = Blueprint->UbergraphPages[0];
    }

    if (!Graph)
    {
        Result->SetBoolField("success", false);
        Result->SetStringField("error", "Graph not found");
        return Result;
    }

    // Find nodes
    UK2Node* SourceNode = FindNodeById(Graph, SourceNodeId);
    UK2Node* TargetNode = FindNodeById(Graph, TargetNodeId);

    if (!SourceNode || !TargetNode)
    {
        Result->SetBoolField("success", false);
        Result->SetStringField("error", "Node not found");
        return Result;
    }

    // Trouver pins
    UEdGraphPin* SourcePin = FindPinByName(SourceNode, SourcePinName, EGPD_Output);
    UEdGraphPin* TargetPin = FindPinByName(TargetNode, TargetPinName, EGPD_Input);

    if (!SourcePin || !TargetPin)
    {
        Result->SetBoolField("success", false);
        Result->SetStringField("error", "Pin not found");
        return Result;
    }

    // Use the schema to validate the connection (handles promotion, inheritance, etc.)
    const UEdGraphSchema_K2* Schema = GetDefault<UEdGraphSchema_K2>();
    FPinConnectionResponse ConnectionResponse = Schema->CanCreateConnection(SourcePin, TargetPin);

    if (ConnectionResponse.Response == CONNECT_RESPONSE_DISALLOW)
    {
        Result->SetBoolField("success", false);
        Result->SetStringField("error", FString::Printf(TEXT("Pins not compatible: %s"), *ConnectionResponse.Message.ToString()));
        return Result;
    }

    // Create connection
    SourcePin->Modify();
    TargetPin->Modify();
    
    // In some cases we might need to use TryCreateConnection to trigger specialized node logic 
    // (like type promotion in Comparison nodes)
    if (!Schema->TryCreateConnection(SourcePin, TargetPin))
    {
        // Fallback to manual if Try returned false but didn't disallow
        SourcePin->MakeLinkTo(TargetPin);
    }

    // Notify nodes of the connection changed (important for K2Nodes to update internals)
    SourceNode->PinConnectionListChanged(SourcePin);
    TargetNode->PinConnectionListChanged(TargetPin);

    // Recompile
    Blueprint->MarkPackageDirty();
    FKismetEditorUtilities::CompileBlueprint(Blueprint);

    // Return
    Result->SetBoolField("success", true);

    TSharedPtr<FJsonObject> ConnectionInfo = MakeShared<FJsonObject>();
    ConnectionInfo->SetStringField("source_node", SourceNodeId);
    ConnectionInfo->SetStringField("source_pin", SourcePinName);
    ConnectionInfo->SetStringField("target_node", TargetNodeId);
    ConnectionInfo->SetStringField("target_pin", TargetPinName);
    ConnectionInfo->SetStringField("connection_type", SourcePin->PinType.PinCategory.ToString());
    
    if (!ConnectionResponse.Message.IsEmpty())
    {
        ConnectionInfo->SetStringField("message", ConnectionResponse.Message.ToString());
    }

    Result->SetObjectField("connection", ConnectionInfo);

    return Result;
}

UK2Node* FBPConnector::FindNodeById(UEdGraph* Graph, const FString& NodeId)
{
    if (!Graph)
    {
        return nullptr;
    }

    for (UEdGraphNode* Node : Graph->Nodes)
    {
        if (!Node)
        {
            continue;
        }

        // Try matching by NodeGuid first
        if (Node->NodeGuid.ToString().Equals(NodeId, ESearchCase::IgnoreCase))
        {
            UK2Node* K2Node = Cast<UK2Node>(Node);
            return K2Node;  // Return even if nullptr (caller will handle)
        }

        // Try matching by GetName()
        if (Node->GetName().Equals(NodeId, ESearchCase::IgnoreCase))
        {
            UK2Node* K2Node = Cast<UK2Node>(Node);
            return K2Node;  // Return even if nullptr (caller will handle)
        }
    }

    return nullptr;
}

UEdGraphPin* FBPConnector::FindPinByName(UK2Node* Node, const FString& PinName, EEdGraphPinDirection Direction)
{
    if (!Node) return nullptr;

    const UEdGraphSchema_K2* Schema = GetDefault<UEdGraphSchema_K2>();

    // Strategy 1: Exact search
    for (UEdGraphPin* Pin : Node->Pins)
    {
        if (Pin->Direction == Direction && Pin->PinName.ToString().Equals(PinName, ESearchCase::CaseSensitive))
        {
            return Pin;
        }
    }

    // Strategy 2: Case-insensitive search
    for (UEdGraphPin* Pin : Node->Pins)
    {
        if (Pin->Direction == Direction && Pin->PinName.ToString().Equals(PinName, ESearchCase::IgnoreCase))
        {
            return Pin;
        }
    }

    // Strategy 3: Handle execution pin aliases
    if (PinName.Equals(TEXT("execute"), ESearchCase::IgnoreCase))
    {
        for (UEdGraphPin* Pin : Node->Pins)
        {
            if (Pin->Direction == Direction && Pin->PinType.PinCategory == UEdGraphSchema_K2::PC_Exec)
            {
                // For input pins, any exec pin is usually the entry
                if (Direction == EGPD_Input) return Pin;

                // For output pins, favor "then" or "execute"
                if (Pin->PinName.ToString().Equals(TEXT("then"), ESearchCase::IgnoreCase)) return Pin;
                if (Pin->PinName.ToString().Equals(TEXT("execute"), ESearchCase::IgnoreCase)) return Pin;
            }
        }
    }

    return nullptr;
}
