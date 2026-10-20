#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "FactoryEquipmentIndicator.generated.h"

class UTextRenderComponent;
class UPointLightComponent;
class USceneComponent;
class UPrimitiveComponent;

// Visual overlay. The USDStageActor retains ownership of the imported USD geometry.
UCLASS()
class FACTORYTWIN_API AFactoryEquipmentIndicator : public AActor
{
	GENERATED_BODY()

public:
	AFactoryEquipmentIndicator();
	void Initialize(const FString& InId, const FString& InKind, USceneComponent* InUsdComponent);
	void Initialize(const FString& InId, const FString& InKind, USceneComponent* InUsdComponent,
		const FVector& PrimWorldPositionCm, USceneComponent* InUsdGeometryComponent = nullptr);
	void InitializeVisuals(const FString& InId, const FString& InKind, const FVector& PrimWorldPositionCm,
		USceneComponent* InIdComponent, const TArray<USceneComponent*>& InGeneratedGeometryComponents);
	bool SetEquipmentState(const FString& NewState);
	void SetPositionMeters(const FVector& PositionMeters);
	void SetPositionCentimeters(const FVector& PositionCentimeters);
	void ResetIndicator();
	void SetActiveInScenario(bool bActive);
	void FaceCamera(const FVector& CameraLocation);
	const FString& GetEquipmentId() const { return EquipmentId; }
	const FString& GetKind() const { return Kind; }
	const FString& GetState() const { return State; }
	int32 GetGeometryRootCount() const { return GeometryRoots.Num(); }
	int32 GetVisiblePrimitiveCount() const;
	FBox GetGeometryBounds() const;
	bool VerifyGeometryPlacement(float ToleranceCm, FString& OutError) const;
	bool IsGeneratedGeometryHidden() const;

private:
	UPROPERTY(VisibleAnywhere)
	TObjectPtr<USceneComponent> Root;

	UPROPERTY(VisibleAnywhere)
	TObjectPtr<UTextRenderComponent> Label;

	UPROPERTY(VisibleAnywhere)
	TObjectPtr<UPointLightComponent> StateLight;

	TWeakObjectPtr<USceneComponent> UsdComponent;
	TArray<TWeakObjectPtr<USceneComponent>> GeometryRoots;
	TArray<TWeakObjectPtr<USceneComponent>> MovementRoots;
	TArray<FVector> InitialMovementRootLocations;
	TArray<TWeakObjectPtr<UPrimitiveComponent>> RenderedPrimitives;
	FString EquipmentId;
	FString Kind;
	FString State = TEXT("Idle");
	FVector IndicatorOffset = FVector(0.0, 0.0, 140.0);
	FVector InitialComponentLocation = FVector::ZeroVector;
	FVector InitialOverlayLocation = FVector::ZeroVector;
	FVector PrimOriginCm = FVector::ZeroVector;
	FVector CurrentOriginCm = FVector::ZeroVector;
};
