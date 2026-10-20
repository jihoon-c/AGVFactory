#include "FactoryEventReplayComponent.h"

#include "FactoryEquipmentIndicator.h"
#include "FactoryEquipmentRegistrySubsystem.h"
#include "Dom/JsonObject.h"
#include "Misc/FileHelper.h"
#include "Misc/Paths.h"
#include "Serialization/JsonReader.h"
#include "Serialization/JsonSerializer.h"

UFactoryEventReplayComponent::UFactoryEventReplayComponent()
{
	PrimaryComponentTick.bCanEverTick = false;
}

bool UFactoryEventReplayComponent::LoadJsonl(const FString& FullPath,
	UFactoryEquipmentRegistrySubsystem* Registry, FString& OutError)
{
	check(IsInGameThread());
	OutError.Empty();
	bPlaying = false;
	bLoaded = false;
	Events.Reset();
	NextEventIndex = 0;
	CurrentTimeMs = 0.0;
	if (!IsValid(Registry) || Registry->NumBindings() != 5)
	{
		OutError = TEXT("Replay requires all five manifest-to-USD bindings");
		LastError = OutError;
		return false;
	}
	TArray<FString> Lines;
	if (!FFileHelper::LoadFileToStringArray(Lines, *FullPath))
	{
		OutError = FString::Printf(TEXT("Cannot read replay JSONL: %s"), *FullPath);
		LastError = OutError;
		return false;
	}
	TArray<FFactoryReplayEvent> Parsed;
	int64 LastTime = -1;
	int32 PreviousId = 0;
	for (int32 Index = 0; Index < Lines.Num(); ++Index)
	{
		const FString Line = Lines[Index].TrimStartAndEnd();
		if (Line.IsEmpty())
		{
			OutError = FString::Printf(TEXT("Blank JSONL event at line %d"), Index + 1);
			break;
		}
		TSharedPtr<FJsonObject> Json;
		if (!FJsonSerializer::Deserialize(TJsonReaderFactory<>::Create(Line), Json) || !Json.IsValid())
		{
			OutError = FString::Printf(TEXT("Malformed JSON at line %d"), Index + 1);
			break;
		}
		FFactoryReplayEvent Event;
		int32 Version = 0;
		int32 EventId = 0;
		double TimeValue = -1.0;
		if (!Json->TryGetNumberField(TEXT("schema_version"), Version) || Version != 1 ||
			!Json->TryGetNumberField(TEXT("event_id"), EventId) ||
			!Json->TryGetNumberField(TEXT("simulation_time_ms"), TimeValue) ||
			!Json->TryGetStringField(TEXT("equipment_id"), Event.EquipmentId) ||
			!Json->TryGetStringField(TEXT("event_type"), Event.EventType) ||
			!FMath::IsFinite(TimeValue) || TimeValue < 0.0 || TimeValue != FMath::FloorToDouble(TimeValue) ||
			TimeValue > static_cast<double>(MAX_int64))
		{
			OutError = FString::Printf(TEXT("Invalid JSONL schema, fields or timestamp at line %d"), Index + 1);
			break;
		}
		Event.SimulationTimeMs = static_cast<int64>(TimeValue);
		Event.EventId = EventId;
		if (EventId != PreviousId + 1 || Event.SimulationTimeMs < LastTime)
		{
			OutError = FString::Printf(TEXT("Duplicate/gap event_id or out-of-order simulation_time_ms at line %d"), Index + 1);
			break;
		}
		if (!IsValid(Registry->FindEquipment(Event.EquipmentId)))
		{
			OutError = FString::Printf(TEXT("Unknown equipment ID '%s' at line %d"), *Event.EquipmentId, Index + 1);
			break;
		}
		const bool bAgv = Event.EquipmentId.StartsWith(TEXT("AGV"));
		if (Event.EventType == TEXT("state_changed"))
		{
			if (!Json->TryGetStringField(TEXT("state"), Event.State) ||
				(bAgv ? (Event.State != TEXT("Idle") && Event.State != TEXT("Moving")) :
				(Event.State != TEXT("Idle") && Event.State != TEXT("Busy") && Event.State != TEXT("Down"))))
			{
				OutError = FString::Printf(TEXT("Invalid equipment state at line %d"), Index + 1);
				break;
			}
			if (bAgv && Json->HasField(TEXT("waypoint")) &&
				!Json->TryGetStringField(TEXT("waypoint"), Event.Waypoint))
			{
				OutError = FString::Printf(TEXT("Non-string AGV waypoint at line %d"), Index + 1);
				break;
			}
			if (!Event.Waypoint.IsEmpty())
			{
				FVector Ignored;
				if (!Registry->FindWaypoint(Event.Waypoint, Ignored))
				{
					OutError = FString::Printf(TEXT("Unknown AGV waypoint '%s' at line %d"), *Event.Waypoint, Index + 1);
					break;
				}
			}
		}
		else if (Event.EventType == TEXT("job_arrived") || Event.EventType == TEXT("job_completed"))
		{
			// Informational events are counted for timeline/cursor accuracy; Python owns the jobs.
		}
		else if (bAgv && (Event.EventType == TEXT("position_changed") || Event.EventType == TEXT("waypoint")))
		{
			const TArray<TSharedPtr<FJsonValue>>* Coords = nullptr;
			if (!Json->TryGetArrayField(TEXT("position_m"), Coords) || !Coords || Coords->Num() != 3 ||
				!(*Coords)[0]->TryGetNumber(Event.PositionMeters.X) ||
				!(*Coords)[1]->TryGetNumber(Event.PositionMeters.Y) ||
				!(*Coords)[2]->TryGetNumber(Event.PositionMeters.Z) ||
				Event.PositionMeters.ContainsNaN())
			{
				OutError = FString::Printf(TEXT("Invalid AGV position_m [x,y,z] at line %d"), Index + 1);
				break;
			}
			Event.bHasPosition = true;
		}
		else
		{
			OutError = FString::Printf(TEXT("Unsupported event_type '%s' at line %d"), *Event.EventType, Index + 1);
			break;
		}
		Parsed.Add(MoveTemp(Event));
		PreviousId = EventId;
		LastTime = Parsed.Last().SimulationTimeMs;
	}
	if (OutError.IsEmpty() && Parsed.IsEmpty())
	{
		OutError = TEXT("Replay file contains no events");
	}
	if (!OutError.IsEmpty())
	{
		LastError = OutError;
		return false;
	}
	Events = MoveTemp(Parsed);
	bSingleAgv = FPaths::GetCleanFilename(FullPath).Contains(TEXT("agv_1"));
	bLoaded = true;
	LastError.Empty();
	ResetReplay(Registry);
	return true;
}

void UFactoryEventReplayComponent::ResetReplay(UFactoryEquipmentRegistrySubsystem* Registry)
{
	check(IsInGameThread());
	bPlaying = false;
	CurrentTimeMs = 0;
	NextEventIndex = 0;
	if (IsValid(Registry))
	{
		static const TCHAR* Ids[] = { TEXT("M01"), TEXT("M02"), TEXT("QC01"), TEXT("AGV01"), TEXT("AGV02") };
		for (const TCHAR* Id : Ids)
		{
			if (AFactoryEquipmentIndicator* Indicator = Registry->FindEquipment(Id))
			{
				Indicator->ResetIndicator();
					Indicator->SetActiveInScenario(!(bSingleAgv && FString(Id) == TEXT("AGV02")));
			}
		}
	}
}

void UFactoryEventReplayComponent::AdvanceReplay(double DeltaSeconds, UFactoryEquipmentRegistrySubsystem* Registry)
{
	check(IsInGameThread());
	if (!bLoaded || !bPlaying || !IsValid(Registry))
	{
		return;
	}
	CurrentTimeMs += FMath::Max(0.0, DeltaSeconds) * PlaybackSpeed * 1000.0;
	while (NextEventIndex < Events.Num() && Events[NextEventIndex].SimulationTimeMs <= CurrentTimeMs)
	{
		if (!ApplyEvent(Events[NextEventIndex], Registry))
		{
			bPlaying = false;
			return;
		}
		++NextEventIndex;
	}
	if (NextEventIndex == Events.Num())
	{
		bPlaying = false;
	}
}

bool UFactoryEventReplayComponent::ApplyEvent(const FFactoryReplayEvent& Event,
	UFactoryEquipmentRegistrySubsystem* Registry)
{
	AFactoryEquipmentIndicator* Indicator = Registry->FindEquipment(Event.EquipmentId);
	if (!IsValid(Indicator))
	{
		LastError = FString::Printf(TEXT("Replay lost registered UE Actor: %s"), *Event.EquipmentId);
		UE_LOG(LogTemp, Error, TEXT("FactoryTwin: %s"), *LastError);
		return false;
	}
	if (!Event.State.IsEmpty() && !Indicator->SetEquipmentState(Event.State))
	{
		LastError = FString::Printf(TEXT("Invalid state during replay: %s"), *Event.EquipmentId);
		UE_LOG(LogTemp, Error, TEXT("FactoryTwin: %s"), *LastError);
		return false;
	}
	if (Event.bHasPosition)
	{
		Indicator->SetPositionMeters(Event.PositionMeters);
	}
	else if (!Event.Waypoint.IsEmpty() && Event.State == TEXT("Idle"))
	{
		FVector LocationCentimeters;
		if (Registry->FindWaypoint(Event.Waypoint, LocationCentimeters))
		{
			Indicator->SetPositionCentimeters(LocationCentimeters);
		}
	}
	return true;
}
