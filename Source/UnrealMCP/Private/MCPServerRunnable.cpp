#include "MCPServerRunnable.h"
#include "EpicUnrealMCPBridge.h"
#include "Sockets.h"
#include "SocketSubsystem.h"
#include "Interfaces/IPv4/IPv4Address.h"
#include "Dom/JsonObject.h"
#include "Dom/JsonValue.h"
#include "Serialization/JsonSerializer.h"
#include "Serialization/JsonReader.h"
#include "JsonObjectConverter.h"
#include "Misc/ScopeLock.h"
#include "HAL/PlatformTime.h"

FMCPServerRunnable::FMCPServerRunnable(UEpicUnrealMCPBridge* InBridge, TSharedPtr<FSocket> InListenerSocket)
    : Bridge(InBridge)
    , ListenerSocket(InListenerSocket)
    , bRunning(true)
{
    UE_LOG(LogTemp, Display, TEXT("MCPServerRunnable: Created server runnable"));
}

FMCPServerRunnable::~FMCPServerRunnable()
{
    // Note: We don't delete the sockets here as they're owned by the bridge
}

bool FMCPServerRunnable::Init()
{
    return true;
}

uint32 FMCPServerRunnable::Run()
{
    UE_LOG(LogTemp, Display, TEXT("MCPServerRunnable: Server thread starting..."));
    
    while (bRunning)
    {
        // UE_LOG(LogTemp, Display, TEXT("MCPServerRunnable: Waiting for client connection..."));
        
        bool bPending = false;
        if (ListenerSocket->HasPendingConnection(bPending) && bPending)
        {
            UE_LOG(LogTemp, Display, TEXT("MCPServerRunnable: Client connection pending, accepting..."));
            
            ClientSocket = MakeShareable(ListenerSocket->Accept(TEXT("MCPClient")));
            if (ClientSocket.IsValid())
            {
                UE_LOG(LogTemp, Display, TEXT("MCPServerRunnable: Client connection accepted"));
                
                // Set socket options to improve connection stability
                ClientSocket->SetNoDelay(true);
                int32 SocketBufferSize = 65536;  // 64KB buffer
                ClientSocket->SetSendBufferSize(SocketBufferSize, SocketBufferSize);
                ClientSocket->SetReceiveBufferSize(SocketBufferSize, SocketBufferSize);
                
                uint8 Buffer[8192];
                // Buffer for receiving message length (4 bytes)
                uint8 LengthBuffer[4];
                while (bRunning && ClientSocket->GetConnectionState() == SCS_Connected)
                {
                    // First, read the 4-byte message length
                    int32 LengthBytesRead = 0;
                    while (LengthBytesRead < 4 && bRunning) {
                        int32 CurrentBytesRead = 0;
                        if (!ClientSocket->Recv(LengthBuffer + LengthBytesRead, 4 - LengthBytesRead, CurrentBytesRead)) {
                            int32 LastError = (int32)ISocketSubsystem::Get()->GetLastErrorCode();
                            if (LastError != SE_EWOULDBLOCK && LastError != SE_EINTR) {
                                UE_LOG(LogTemp, Warning, TEXT("MCPServerRunnable: Failed to read message length. Last error code: %d"), LastError);
                                break;
                            }
                            // Small sleep to prevent tight loop when no data
                            FPlatformProcess::Sleep(0.01f);
                            continue;
                        }
                        
                        if (CurrentBytesRead == 0) {
                            UE_LOG(LogTemp, Display, TEXT("MCPServerRunnable: Client disconnected while reading length"));
                            break;
                        }

                        LengthBytesRead += CurrentBytesRead;
                    }

                    if (LengthBytesRead != 4) {
                        if (bRunning && ClientSocket->GetConnectionState() == SCS_Connected) {
                            UE_LOG(LogTemp, Warning, TEXT("MCPServerRunnable: Failed to read complete message length (%d/4 bytes)"), LengthBytesRead);
                        }
                        break;
                    }

                    // Convert length from big-endian bytes to integer
                    int32 MessageLength = (LengthBuffer[0] << 24) | (LengthBuffer[1] << 16) | (LengthBuffer[2] << 8) | LengthBuffer[3];
                    UE_LOG(LogTemp, Display, TEXT("MCPServerRunnable: Expecting message of length %d bytes"), MessageLength);

                    // Validate message length to prevent excessive memory allocation
                    if (MessageLength <= 0 || MessageLength > 1024 * 1024 * 10) {  // Max 10MB message
                        UE_LOG(LogTemp, Warning, TEXT("MCPServerRunnable: Invalid message length: %d"), MessageLength);
                        break;
                    }

                    // Allocate buffer for the complete message
                    TArray<uint8> MessageBuffer;
                    MessageBuffer.SetNumUninitialized(MessageLength + 1);

                    // Read the complete message
                    int32 MessageBytesRead = 0;
                    while (MessageBytesRead < MessageLength && bRunning) {
                        int32 CurrentBytesRead = 0;
                        int32 BytesToRead = FMath::Min(MessageLength - MessageBytesRead, 8192);
                        if (!ClientSocket->Recv(Buffer, BytesToRead, CurrentBytesRead)) {
                            int32 LastError = (int32)ISocketSubsystem::Get()->GetLastErrorCode();
                            if (LastError != SE_EWOULDBLOCK && LastError != SE_EINTR) {
                                UE_LOG(LogTemp, Warning, TEXT("MCPServerRunnable: Failed to read message data. Last error code: %d"), LastError);
                                break;
                            }
                            FPlatformProcess::Sleep(0.01f);
                            continue;
                        }
                        
                        if (CurrentBytesRead == 0) {
                            UE_LOG(LogTemp, Display, TEXT("MCPServerRunnable: Client disconnected while reading data"));
                            break;
                        }

                        FMemory::Memcpy(MessageBuffer.GetData() + MessageBytesRead, Buffer, CurrentBytesRead);
                        MessageBytesRead += CurrentBytesRead;
                    }

                    if (MessageBytesRead != MessageLength) {
                        UE_LOG(LogTemp, Warning, TEXT("MCPServerRunnable: Failed to read complete message (%d/%d bytes)"), MessageBytesRead, MessageLength);
                        break;
                    }

                    // Null terminate and convert to string
                    MessageBuffer[MessageLength] = '\0';
                    FString ReceivedText = UTF8_TO_TCHAR(MessageBuffer.GetData());
                    UE_LOG(LogTemp, Display, TEXT("MCPServerRunnable: Received complete message: %s"), *ReceivedText);

                    // Parse JSON
                    TSharedPtr<FJsonObject> JsonObject;
                    TSharedRef<TJsonReader<>> Reader = TJsonReaderFactory<>::Create(ReceivedText);
                    
                    if (FJsonSerializer::Deserialize(Reader, JsonObject))
                    {
                        // Get command type
                        FString CommandType;
                        if (JsonObject->TryGetStringField(TEXT("type"), CommandType))
                        {
                            UE_LOG(LogTemp, Display, TEXT("MCPServerRunnable: Executing command: %s"), *CommandType);

                            // Execute command
                            FString Response = Bridge->ExecuteCommand(CommandType, JsonObject->GetObjectField(TEXT("params")));

                            UE_LOG(LogTemp, Display, TEXT("MCPServerRunnable: Command executed, response length: %d"), Response.Len());

                            // Log response for debugging (truncated for large responses)
                            FString LogResponse = Response.Len() > 200 ? Response.Left(200) + TEXT("...") : Response;
                            UE_LOG(LogTemp, Display, TEXT("MCPServerRunnable: Sending response (%d bytes): %s"),
                                   Response.Len(), *LogResponse);

                            // Prepend 4-byte big-endian length header before sending response
                            FTCHARToUTF8 UTF8Response(*Response);
                            const uint8* DataToSend = (const uint8*)UTF8Response.Get();
                            int32 TotalDataSize = UTF8Response.Length();

                            // Create length header (4 bytes, big-endian)
                            uint8 LengthHeader[4];
                            LengthHeader[0] = (TotalDataSize >> 24) & 0xFF;
                            LengthHeader[1] = (TotalDataSize >> 16) & 0xFF;
                            LengthHeader[2] = (TotalDataSize >> 8) & 0xFF;
                            LengthHeader[3] = TotalDataSize & 0xFF;

                            // Send length header first
                            int32 HeaderBytesSent = 0;
                            bool bHeaderSuccess = true;
                            while (HeaderBytesSent < 4 && bRunning) {
                                int32 BytesSent = 0;
                                bool bSendResult = ClientSocket->Send(LengthHeader + HeaderBytesSent, 4 - HeaderBytesSent, BytesSent);
                                
                                if (!bSendResult) {
                                    int32 LastError = (int32)ISocketSubsystem::Get()->GetLastErrorCode();
                                    if (LastError == SE_EWOULDBLOCK || LastError == SE_EINTR) {
                                        FPlatformProcess::Sleep(0.01f);
                                        continue;
                                    }
                                    UE_LOG(LogTemp, Error, TEXT("MCPServerRunnable: Failed to send length header after %d/4 bytes - Error code: %d"),
                                           HeaderBytesSent, LastError);
                                    bHeaderSuccess = false;
                                    break;
                                }
                                
                                HeaderBytesSent += BytesSent;
                            }

                            if (!bHeaderSuccess) {
                                break;
                            }

                            // Then send the actual response data
                            int32 TotalBytesSent = 0;
                            bool bSuccess = true;

                            // Send all data in a loop (TCP may not send everything at once)
                            while (TotalBytesSent < TotalDataSize && bRunning)
                            {
                                int32 BytesSent = 0;
                                bool bSendResult = ClientSocket->Send(DataToSend + TotalBytesSent,
                                                                      TotalDataSize - TotalBytesSent,
                                                                      BytesSent);

                                if (!bSendResult)
                                {
                                    int32 LastError = (int32)ISocketSubsystem::Get()->GetLastErrorCode();
                                    if (LastError == SE_EWOULDBLOCK || LastError == SE_EINTR) {
                                        FPlatformProcess::Sleep(0.01f);
                                        continue;
                                    }
                                    UE_LOG(LogTemp, Error, TEXT("MCPServerRunnable: Failed to send response after %d/%d bytes - Error code: %d"),
                                           TotalBytesSent, TotalDataSize, LastError);
                                    bSuccess = false;
                                    break;
                                }

                                TotalBytesSent += BytesSent;
                            }

                            if (bSuccess)
                            {
                                UE_LOG(LogTemp, Display, TEXT("MCPServerRunnable: Response sent successfully (%d bytes)"),
                                       TotalBytesSent);
                            }
                        }
                        else
                        {
                            UE_LOG(LogTemp, Warning, TEXT("MCPServerRunnable: Missing 'type' field in command"));
                        }
                    }
                    else
                    {
                        FString TruncatedMsg = ReceivedText.Left(100);
                        if (ReceivedText.Len() > 100) TruncatedMsg += TEXT("...");
                        UE_LOG(LogTemp, Warning, TEXT("MCPServerRunnable: Failed to parse JSON from message (length %d): '%s'"), MessageLength, *TruncatedMsg);
                    }
                }
                
                UE_LOG(LogTemp, Display, TEXT("MCPServerRunnable: Client disconnected"));
            }
            else
            {
                UE_LOG(LogTemp, Warning, TEXT("MCPServerRunnable: Failed to accept client connection"));
            }
        }
        
        // Small sleep to prevent tight loop
        FPlatformProcess::Sleep(0.1f);
    }
    
    UE_LOG(LogTemp, Display, TEXT("MCPServerRunnable: Server thread stopping"));
    return 0;
}

void FMCPServerRunnable::Stop()
{
    bRunning = false;
}

void FMCPServerRunnable::Exit()
{
}

void FMCPServerRunnable::HandleClientConnection(TSharedPtr<FSocket> InClientSocket)
{
    if (!InClientSocket.IsValid())
    {
        UE_LOG(LogTemp, Error, TEXT("MCPServerRunnable: Invalid client socket passed to HandleClientConnection"));
        return;
    }

    UE_LOG(LogTemp, Display, TEXT("MCPServerRunnable: Starting to handle client connection"));
    
    // Set socket options for better connection stability
    InClientSocket->SetNonBlocking(false);
    UE_LOG(LogTemp, Display, TEXT("MCPServerRunnable: Set socket to blocking mode"));
    
    // Properly read full message with timeout
    const int32 MaxBufferSize = 4096;
    uint8 Buffer[MaxBufferSize];
    // Buffer for receiving message length (4 bytes)
    uint8 LengthBuffer[4];
    
    UE_LOG(LogTemp, Display, TEXT("MCPServerRunnable: Starting message receive loop"));
    
    while (bRunning && InClientSocket.IsValid())
    {
        // Log socket state
        bool bIsConnected = InClientSocket->GetConnectionState() == SCS_Connected;
        UE_LOG(LogTemp, Display, TEXT("MCPServerRunnable: Socket state - Connected: %s"), 
               bIsConnected ? TEXT("true") : TEXT("false"));
        
        // First, read the 4-byte message length
        int32 LengthBytesRead = 0;
        while (LengthBytesRead < 4) {
            int32 CurrentBytesRead = 0;
            if (!InClientSocket->Recv(LengthBuffer + LengthBytesRead, 4 - LengthBytesRead, CurrentBytesRead, ESocketReceiveFlags::None)) {
                int32 LastError = (int32)ISocketSubsystem::Get()->GetLastErrorCode();
                if (LastError != SE_EWOULDBLOCK && LastError != SE_EINTR) {
                    UE_LOG(LogTemp, Warning, TEXT("MCPServerRunnable: Failed to read message length. Last error code: %d"), LastError);
                    break;
                }
                // Small sleep to prevent tight loop when no data
                FPlatformProcess::Sleep(0.01f);
                continue;
            }
            LengthBytesRead += CurrentBytesRead;
        }

        if (LengthBytesRead != 4) {
            UE_LOG(LogTemp, Warning, TEXT("MCPServerRunnable: Failed to read complete message length (%d/4 bytes)"), LengthBytesRead);
            break;
        }

        // Convert length from big-endian bytes to integer
        int32 MessageLength = (LengthBuffer[0] << 24) | (LengthBuffer[1] << 16) | (LengthBuffer[2] << 8) | LengthBuffer[3];
        UE_LOG(LogTemp, Display, TEXT("MCPServerRunnable: Expecting message of length %d bytes"), MessageLength);

        // Validate message length to prevent excessive memory allocation
        if (MessageLength <= 0 || MessageLength > 1024 * 1024) {  // Max 1MB message
            UE_LOG(LogTemp, Warning, TEXT("MCPServerRunnable: Invalid message length: %d"), MessageLength);
            break;
        }

        // Allocate buffer for the complete message
        TUniquePtr<uint8[]> MessageBuffer = MakeUnique<uint8[]>(MessageLength + 1);  // +1 for null terminator

        // Read the complete message
        int32 MessageBytesRead = 0;
        while (MessageBytesRead < MessageLength) {
            int32 CurrentBytesRead = 0;
            int32 BytesToRead = FMath::Min(MessageLength - MessageBytesRead, MaxBufferSize - 1);
            if (!InClientSocket->Recv(Buffer, BytesToRead, CurrentBytesRead, ESocketReceiveFlags::None)) {
                int32 LastError = (int32)ISocketSubsystem::Get()->GetLastErrorCode();
                if (LastError != SE_EWOULDBLOCK && LastError != SE_EINTR) {
                    UE_LOG(LogTemp, Warning, TEXT("MCPServerRunnable: Failed to read message data. Last error code: %d"), LastError);
                    break;
                }
                // Small sleep to prevent tight loop when no data
                FPlatformProcess::Sleep(0.01f);
                continue;
            }
            FMemory::Memcpy(MessageBuffer.Get() + MessageBytesRead, Buffer, CurrentBytesRead);
            MessageBytesRead += CurrentBytesRead;
        }

        if (MessageBytesRead != MessageLength) {
            UE_LOG(LogTemp, Warning, TEXT("MCPServerRunnable: Failed to read complete message (%d/%d bytes)"), MessageBytesRead, MessageLength);
            break;
        }

        // Null terminate and convert to string
        MessageBuffer[MessageLength] = '\0';
        FString ReceivedData = UTF8_TO_TCHAR(MessageBuffer.Get());
        
        // Process the complete message
        ProcessMessage(InClientSocket, ReceivedData);
    }
    
    UE_LOG(LogTemp, Display, TEXT("MCPServerRunnable: Exited message receive loop"));
}

void FMCPServerRunnable::ProcessMessage(TSharedPtr<FSocket> Client, const FString& Message)
{
    UE_LOG(LogTemp, Display, TEXT("MCPServerRunnable: Processing message: %s"), *Message);
    
    // Parse message as JSON
    TSharedPtr<FJsonObject> JsonMessage;
    TSharedRef<TJsonReader<>> Reader = TJsonReaderFactory<>::Create(Message);
    
    if (!FJsonSerializer::Deserialize(Reader, JsonMessage) || !JsonMessage.IsValid())
    {
        UE_LOG(LogTemp, Warning, TEXT("MCPServerRunnable: Failed to parse message as JSON"));
        return;
    }
    
    // Extract command type and parameters using MCP protocol format
    FString CommandType;
    TSharedPtr<FJsonObject> Params = MakeShareable(new FJsonObject());
    
    if (!JsonMessage->TryGetStringField(TEXT("command"), CommandType))
    {
        UE_LOG(LogTemp, Warning, TEXT("MCPServerRunnable: Message missing 'command' field"));
        return;
    }
    
    // Parameters are optional in MCP protocol
    if (JsonMessage->HasField(TEXT("params")))
    {
        TSharedPtr<FJsonValue> ParamsValue = JsonMessage->TryGetField(TEXT("params"));
        if (ParamsValue.IsValid() && ParamsValue->Type == EJson::Object)
        {
            Params = ParamsValue->AsObject();
        }
    }
    
    UE_LOG(LogTemp, Display, TEXT("MCPServerRunnable: Executing command: %s"), *CommandType);
    
    // Execute command
    FString Response = Bridge->ExecuteCommand(CommandType, Params);
    
    // Prepend 4-byte big-endian length header before sending response
    FTCHARToUTF8 UTF8Response(*Response);
    const uint8* DataToSend = (const uint8*)UTF8Response.Get();
    int32 TotalDataSize = UTF8Response.Length();

    // Create length header (4 bytes, big-endian)
    uint8 LengthHeader[4];
    LengthHeader[0] = (TotalDataSize >> 24) & 0xFF;
    LengthHeader[1] = (TotalDataSize >> 16) & 0xFF;
    LengthHeader[2] = (TotalDataSize >> 8) & 0xFF;
    LengthHeader[3] = TotalDataSize & 0xFF;

    // Send length header first
    int32 HeaderBytesSent = 0;
    while (HeaderBytesSent < 4) {
        int32 BytesSent = 0;
        if (!Client->Send(LengthHeader + HeaderBytesSent, 4 - HeaderBytesSent, BytesSent)) {
            UE_LOG(LogTemp, Error, TEXT("MCPServerRunnable: Failed to send length header after %d/4 bytes"), HeaderBytesSent);
            return;
        }
        HeaderBytesSent += BytesSent;
        UE_LOG(LogTemp, Display, TEXT("MCPServerRunnable: Sent %d header bytes (%d/4 total)"), BytesSent, HeaderBytesSent);
    }

    // Then send the actual response data
    int32 TotalBytesSent = 0;

    // Send all data in a loop (TCP may not send everything at once)
    while (TotalBytesSent < TotalDataSize)
    {
        int32 BytesSent = 0;
        if (!Client->Send(DataToSend + TotalBytesSent, TotalDataSize - TotalBytesSent, BytesSent))
        {
            UE_LOG(LogTemp, Error, TEXT("MCPServerRunnable: Failed to send response after %d/%d bytes"),
                   TotalBytesSent, TotalDataSize);
            return;
        }

        TotalBytesSent += BytesSent;
        UE_LOG(LogTemp, Display, TEXT("MCPServerRunnable: Sent %d bytes (%d/%d total)"),
               BytesSent, TotalBytesSent, TotalDataSize);
    }

    UE_LOG(LogTemp, Display, TEXT("MCPServerRunnable: Response sent successfully (%d bytes)"),
           TotalBytesSent);
} 