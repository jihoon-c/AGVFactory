#pragma once

#include "CoreMinimal.h"
#include "Components/ActorComponent.h"
#include "FactoryEventReplayComponent.generated.h"

class UFactoryEquipmentRegistrySubsystem;

struct FFactoryReplayEvent
{
	int32 EventId = 0;
	int64 SimulationTimeMs = 0;
	FString EquipmentId;
	FString EventType;
	FString State;
	FString Waypoint;
	bool bHasPosition = false;
	FVector PositionMeters = FVector::ZeroVector;
};

// UE is a read-only consumer of Python runner events. It never simulates jobs or machine transitions.
UCLASS(ClassGroup = (FactoryTwin), meta = (BlueprintSpawnableComponent))
class FACTORYTWIN_API UFactoryEventReplayComponent : public UActorComponent
{
	GENERATED_BODY()

public:
	UFactoryEventReplayComponent();
	bool LoadJsonl(const FString& FullPath, UFactoryEquipmentRegistrySubsystem* Registry, FString& OutError);
	void ResetReplay(UFactoryEquipmentRegistrySubsystem* Registry);
	void AdvanceReplay(double DeltaSeconds, UFactoryEquipmentRegistrySubsystem* Registry);
	void SetPlaying(bool bInPlaying) { bPlaying = bInPlaying; }
	bool IsPlaying() const { return bPlaying; }
	int32 GetCursor() const { return NextEventIndex; }
	int32 GetEventCount() const { return Events.Num(); }
	int64 GetCurrentTimeMs() const { return static_cast<int64>(CurrentTimeMs); }
	bool IsLoaded() const { return bLoaded; }
	const FString& GetLastError() const { return LastError; }

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "FactoryTwin|Replay", meta = (ClampMin = "0.01", ClampMax = "3600.0"))
	double PlaybackSpeed = 60.0;

private:
	TArray<FFactoryReplayEvent> Events;
	int32 NextEventIndex = 0;
	double CurrentTimeMs = 0.0;
	bool bPlaying = false;
	bool bLoaded = false;
	bool bSingleAgv = false;
	FString LastError;
	bool ApplyEvent(const FFactoryReplayEvent& Event, UFactoryEquipmentRegistrySubsystem* Registry);
};
