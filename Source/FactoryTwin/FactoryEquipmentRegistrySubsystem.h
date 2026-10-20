#pragma once

#include "CoreMinimal.h"
#include "Subsystems/WorldSubsystem.h"
#include "FactoryEquipmentRegistrySubsystem.generated.h"

class AFactoryEquipmentIndicator;
class USceneComponent;

struct FFactoryManifestRecord
{
	FString EquipmentId;
	FString PrimPath;
	FString Kind;
};

struct FFactoryEquipmentBinding
{
	FString PrimPath;
	TWeakObjectPtr<AFactoryEquipmentIndicator> Actor;
	TWeakObjectPtr<USceneComponent> UsdComponent;
};

// Explicit mapping: USD metadata is NOT assumed to automatically propagate to UE actors.
UCLASS()
class FACTORYTWIN_API UFactoryEquipmentRegistrySubsystem : public UWorldSubsystem
{
	GENERATED_BODY()

public:
	bool ParseManifest(const FString& FullPath, const FString& ExpectedUsdRoot,
		TArray<FFactoryManifestRecord>& OutRecords, FString& OutError) const;
	bool RegisterBinding(const FFactoryManifestRecord& Record, AFactoryEquipmentIndicator* Actor,
		USceneComponent* UsdComponent, FString& OutError);
	AFactoryEquipmentIndicator* FindEquipment(const FString& EquipmentId) const;
	void SetWaypoint(const FString& Waypoint, const FVector& PositionCentimeters);
	bool FindWaypoint(const FString& Waypoint, FVector& OutPositionCentimeters) const;
	void ClearRegistry();
	int32 NumBindings() const { return Bindings.Num(); }

private:
	TMap<FString, FFactoryEquipmentBinding> Bindings;
	TSet<FString> PrimPaths;
	TMap<FString, FVector> Waypoints;
};
