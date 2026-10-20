#include "FactoryEquipmentRegistrySubsystem.h"

#include "FactoryEquipmentIndicator.h"
#include "Components/SceneComponent.h"
#include "Dom/JsonObject.h"
#include "HAL/FileManager.h"
#include "Misc/FileHelper.h"
#include "Misc/Paths.h"
#include "Serialization/JsonReader.h"
#include "Serialization/JsonSerializer.h"

bool UFactoryEquipmentRegistrySubsystem::ParseManifest(const FString& FullPath, const FString& ExpectedUsdRoot,
	TArray<FFactoryManifestRecord>& OutRecords, FString& OutError) const
{
	OutRecords.Reset();
	FString Contents;
	if (!FFileHelper::LoadFileToString(Contents, *FullPath))
	{
		OutError = FString::Printf(TEXT("Cannot read equipment manifest: %s"), *FullPath);
		return false;
	}
	TSharedPtr<FJsonObject> Document;
	if (!FJsonSerializer::Deserialize(TJsonReaderFactory<>::Create(Contents), Document) || !Document.IsValid())
	{
		OutError = TEXT("Invalid manifest JSON");
		return false;
	}
	int32 Version = 0;
	FString UsdRoot;
	const TArray<TSharedPtr<FJsonValue>>* Equipment = nullptr;
	if (!Document->TryGetNumberField(TEXT("schema_version"), Version) || Version != 1 ||
		!Document->TryGetStringField(TEXT("usd_root"), UsdRoot) ||
		!Document->TryGetArrayField(TEXT("equipment"), Equipment) || Equipment == nullptr)
	{
		OutError = TEXT("Manifest requires schema_version=1, usd_root, equipment[]");
		return false;
	}
	const FString ActualRoot = FPaths::ConvertRelativePathToFull(FPaths::ProjectDir(), UsdRoot);
	if (!FPaths::IsSamePath(ActualRoot, ExpectedUsdRoot))
	{
		OutError = FString::Printf(TEXT("USD root mismatch: %s vs %s"), *ActualRoot, *ExpectedUsdRoot);
		return false;
	}
	TSet<FString> Ids;
	TSet<FString> Paths;
	for (const TSharedPtr<FJsonValue>& Entry : *Equipment)
	{
		const TSharedPtr<FJsonObject> Object = Entry.IsValid() ? Entry->AsObject() : nullptr;
		FFactoryManifestRecord Record;
		if (!Object.IsValid() || !Object->TryGetStringField(TEXT("equipment_id"), Record.EquipmentId) ||
			!Object->TryGetStringField(TEXT("prim_path"), Record.PrimPath) ||
			!Object->TryGetStringField(TEXT("kind"), Record.Kind) ||
			Record.EquipmentId.IsEmpty() || Record.PrimPath.IsEmpty())
		{
			OutError = TEXT("Manifest contains empty/missing equipment_id, prim_path or kind");
			return false;
		}
		if (Ids.Contains(Record.EquipmentId) || Paths.Contains(Record.PrimPath))
		{
			OutError = FString::Printf(TEXT("Duplicate equipment ID or prim path: %s %s"), *Record.EquipmentId, *Record.PrimPath);
			return false;
		}
		const bool bAgv = Record.EquipmentId.StartsWith(TEXT("AGV"));
		const FString RequiredPath = FString::Printf(TEXT("/World/Factory/%s/%s"), bAgv ? TEXT("AGVs") : TEXT("Equipment"), *Record.EquipmentId);
		const FString ExpectedKind = bAgv ? TEXT("agv") :
			(Record.EquipmentId == TEXT("QC01") ? TEXT("inspection") : TEXT("machine"));
		if (Record.PrimPath != RequiredPath || Record.Kind != ExpectedKind)
		{
			OutError = FString::Printf(TEXT("Equipment/prim/kind mismatch: %s"), *Record.EquipmentId);
			return false;
		}
		Ids.Add(Record.EquipmentId);
		Paths.Add(Record.PrimPath);
		OutRecords.Add(MoveTemp(Record));
	}
	static const TCHAR* RequiredIds[] = { TEXT("M01"), TEXT("M02"), TEXT("QC01"), TEXT("AGV01"), TEXT("AGV02") };
	if (OutRecords.Num() != UE_ARRAY_COUNT(RequiredIds))
	{
		OutError = TEXT("Manifest must contain exactly 5 equipment records");
		return false;
	}
	for (const TCHAR* Id : RequiredIds)
	{
		if (!Ids.Contains(Id))
		{
			OutError = FString::Printf(TEXT("Missing required equipment: %s"), Id);
			return false;
		}
	}
	OutError.Empty();
	return true;
}

bool UFactoryEquipmentRegistrySubsystem::RegisterBinding(const FFactoryManifestRecord& Record,
	AFactoryEquipmentIndicator* Actor, USceneComponent* UsdComponent, FString& OutError)
{
	if (Record.EquipmentId.IsEmpty() || Record.PrimPath.IsEmpty() || !IsValid(Actor) ||
		Bindings.Contains(Record.EquipmentId) || PrimPaths.Contains(Record.PrimPath))
	{
		OutError = FString::Printf(TEXT("Binding rejected (missing/duplicate ID, prim or actor): %s"), *Record.EquipmentId);
		return false;
	}
	FFactoryEquipmentBinding Binding;
	Binding.PrimPath = Record.PrimPath;
	Binding.Actor = Actor;
	Binding.UsdComponent = UsdComponent;
	Bindings.Add(Record.EquipmentId, MoveTemp(Binding));
	PrimPaths.Add(Record.PrimPath);
	return true;
}

AFactoryEquipmentIndicator* UFactoryEquipmentRegistrySubsystem::FindEquipment(const FString& EquipmentId) const
{
	if (const FFactoryEquipmentBinding* Found = Bindings.Find(EquipmentId))
	{
		return Found->Actor.Get();
	}
	return nullptr;
}

void UFactoryEquipmentRegistrySubsystem::SetWaypoint(const FString& Waypoint, const FVector& PositionCentimeters)
{
	Waypoints.Add(Waypoint, PositionCentimeters);
}

bool UFactoryEquipmentRegistrySubsystem::FindWaypoint(const FString& Waypoint, FVector& OutPositionCentimeters) const
{
	if (const FVector* Position = Waypoints.Find(Waypoint))
	{
		OutPositionCentimeters = *Position;
		return true;
	}
	return false;
}

void UFactoryEquipmentRegistrySubsystem::ClearRegistry()
{
	Bindings.Reset();
	PrimPaths.Reset();
	Waypoints.Reset();
}
