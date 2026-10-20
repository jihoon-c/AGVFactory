#include "FactoryEquipmentIndicator.h"

#include "Components/SceneComponent.h"
#include "Components/PrimitiveComponent.h"
#include "Components/PointLightComponent.h"
#include "Components/TextRenderComponent.h"

AFactoryEquipmentIndicator::AFactoryEquipmentIndicator()
{
	PrimaryActorTick.bCanEverTick = false;
	Root = CreateDefaultSubobject<USceneComponent>(TEXT("Root"));
	SetRootComponent(Root);
	Label = CreateDefaultSubobject<UTextRenderComponent>(TEXT("IDAndState"));
	Label->SetupAttachment(Root);
	Label->SetHorizontalAlignment(EHTA_Center);
	Label->SetWorldSize(45.0f);
	Label->SetTextRenderColor(FColor(180, 180, 180));
	StateLight = CreateDefaultSubobject<UPointLightComponent>(TEXT("StatusLight"));
	StateLight->SetupAttachment(Root);
	StateLight->SetIntensity(2200.0f);
	StateLight->SetAttenuationRadius(260.0f);
	StateLight->SetLightColor(FLinearColor(0.5f, 0.5f, 0.5f));
}

void AFactoryEquipmentIndicator::Initialize(const FString& InId, const FString& InKind, USceneComponent* InUsdComponent)
{
	Initialize(InId, InKind, InUsdComponent, IsValid(InUsdComponent) ? InUsdComponent->GetComponentLocation() : FVector::ZeroVector);
}

void AFactoryEquipmentIndicator::Initialize(const FString& InId, const FString& InKind,
	USceneComponent* InUsdComponent, const FVector& PrimWorldPositionCm, USceneComponent* InUsdGeometryComponent)
{
	TArray<USceneComponent*> Components;
	if (IsValid(InUsdGeometryComponent))
	{
		Components.Add(InUsdGeometryComponent);
	}
	InitializeVisuals(InId, InKind, PrimWorldPositionCm, InUsdComponent, Components);
}

void AFactoryEquipmentIndicator::InitializeVisuals(const FString& InId, const FString& InKind,
	const FVector& PrimWorldPositionCm, USceneComponent* InIdComponent,
	const TArray<USceneComponent*>& InGeneratedGeometryComponents)
{
	EquipmentId = InId;
	Kind = InKind;
	UsdComponent = InIdComponent;
	GeometryRoots.Reset();
	MovementRoots.Reset();
	InitialMovementRootLocations.Reset();
	RenderedPrimitives.Reset();
	PrimOriginCm = PrimWorldPositionCm;
	CurrentOriginCm = PrimWorldPositionCm;
	TArray<USceneComponent*> UniqueGeometryComponents;
	for (USceneComponent* Component : InGeneratedGeometryComponents)
	{
		if (!IsValid(Component) || UniqueGeometryComponents.Contains(Component))
		{
			continue;
		}
		UniqueGeometryComponents.Add(Component);
		if (UPrimitiveComponent* Primitive = Cast<UPrimitiveComponent>(Component))
		{
			RenderedPrimitives.Add(Primitive);
		}
	}
	// Group referenced USD Xform/Mesh descendants under their topmost exact-source parent.
	// This preserves authored local offsets for complex prefabs when moving an AGV.
	for (USceneComponent* Component : UniqueGeometryComponents)
	{
		bool bHasSelectedAncestor = false;
		for (USceneComponent* Other : UniqueGeometryComponents)
		{
			if (Component != Other && Component->IsAttachedTo(Other))
			{
				bHasSelectedAncestor = true;
				break;
			}
		}
		if (!bHasSelectedAncestor)
		{
			GeometryRoots.Add(Component);
		}
	}
	TArray<USceneComponent*> MovementCandidates = UniqueGeometryComponents;
	if (IsValid(InIdComponent))
	{
		MovementCandidates.AddUnique(InIdComponent);
	}
	for (USceneComponent* Component : MovementCandidates)
	{
		bool bHasSelectedAncestor = false;
		for (USceneComponent* Other : MovementCandidates)
		{
			if (Component != Other && Component->IsAttachedTo(Other))
			{
				bHasSelectedAncestor = true;
				break;
			}
		}
		if (!bHasSelectedAncestor)
		{
			MovementRoots.Add(Component);
			InitialMovementRootLocations.Add(Component->GetComponentLocation());
		}
	}
	if (Kind == TEXT("agv"))
	{
		// USD importer creates Static components. Every generated AGV descendant must allow movement.
		for (USceneComponent* Component : MovementCandidates)
		{
			Component->SetMobility(EComponentMobility::Movable);
		}
	}
	InitialOverlayLocation = PrimWorldPositionCm + IndicatorOffset;
	SetActorLocation(InitialOverlayLocation);
	ResetIndicator();
}

bool AFactoryEquipmentIndicator::SetEquipmentState(const FString& NewState)
{
	const bool bAgv = Kind == TEXT("agv");
	if (bAgv ? (NewState != TEXT("Idle") && NewState != TEXT("Moving")) :
		(NewState != TEXT("Idle") && NewState != TEXT("Busy") && NewState != TEXT("Down")))
	{
		return false;
	}
	State = NewState;
	const FColor Color = State == TEXT("Down") ? FColor::Red : State == TEXT("Busy") ? FColor::Green :
		State == TEXT("Moving") ? FColor::Blue : FColor(170, 170, 170);
	Label->SetText(FText::FromString(EquipmentId + TEXT("  ") + State));
	Label->SetTextRenderColor(Color);
	StateLight->SetLightColor(FLinearColor(Color));
	return true;
}

void AFactoryEquipmentIndicator::SetPositionMeters(const FVector& PositionMeters)
{
	// USD stage uses meters; Unreal uses centimeters. This is a replay-only display update.
	SetPositionCentimeters(PositionMeters * 100.0);
}

void AFactoryEquipmentIndicator::SetPositionCentimeters(const FVector& PositionCentimeters)
{
	CurrentOriginCm = PositionCentimeters;
	const FVector DeltaCm = PositionCentimeters - PrimOriginCm;
	for (int32 Index = 0; Index < MovementRoots.Num(); ++Index)
	{
		if (USceneComponent* GeneratedRoot = MovementRoots[Index].Get())
		{
			GeneratedRoot->SetWorldLocation(InitialMovementRootLocations[Index] + DeltaCm);
		}
	}
	SetActorLocation(PositionCentimeters + IndicatorOffset);
}

void AFactoryEquipmentIndicator::ResetIndicator()
{
	SetEquipmentState(TEXT("Idle"));
	CurrentOriginCm = PrimOriginCm;
	if (Kind == TEXT("agv"))
	{
		for (int32 Index = 0; Index < MovementRoots.Num(); ++Index)
		{
			if (USceneComponent* GeneratedRoot = MovementRoots[Index].Get())
			{
				GeneratedRoot->SetWorldLocation(InitialMovementRootLocations[Index]);
			}
		}
	}
	for (const TWeakObjectPtr<USceneComponent>& GeneratedRoot : GeometryRoots)
	{
		if (USceneComponent* Component = GeneratedRoot.Get())
		{
			Component->SetVisibility(true, true);
		}
	}
	SetActorLocation(InitialOverlayLocation);
	SetActorHiddenInGame(false);
}

void AFactoryEquipmentIndicator::SetActiveInScenario(bool bActive)
{
	SetActorHiddenInGame(!bActive);
	for (const TWeakObjectPtr<USceneComponent>& GeneratedRoot : GeometryRoots)
	{
		if (USceneComponent* Component = GeneratedRoot.Get())
		{
			Component->SetVisibility(bActive, true);
		}
	}
}

int32 AFactoryEquipmentIndicator::GetVisiblePrimitiveCount() const
{
	int32 Count = 0;
	for (const TWeakObjectPtr<UPrimitiveComponent>& Primitive : RenderedPrimitives)
	{
		Count += Primitive.IsValid() && Primitive->IsVisible() ? 1 : 0;
	}
	return Count;
}

FBox AFactoryEquipmentIndicator::GetGeometryBounds() const
{
	FBox Bounds(ForceInit);
	for (const TWeakObjectPtr<UPrimitiveComponent>& Primitive : RenderedPrimitives)
	{
		if (Primitive.IsValid())
		{
			Bounds += Primitive->Bounds.GetBox();
		}
	}
	return Bounds;
}

bool AFactoryEquipmentIndicator::VerifyGeometryPlacement(float ToleranceCm, FString& OutError) const
{
	OutError.Empty();
	if (MovementRoots.Num() == 0 || RenderedPrimitives.IsEmpty())
	{
		OutError = TEXT("No verified generated geometry/roots");
		return false;
	}
	for (int32 Index = 0; Index < MovementRoots.Num(); ++Index)
	{
		const USceneComponent* GeneratedRoot = MovementRoots[Index].Get();
		const FVector Expected = InitialMovementRootLocations[Index] + CurrentOriginCm - PrimOriginCm;
		if (!IsValid(GeneratedRoot) || GeneratedRoot->Mobility != EComponentMobility::Movable ||
			FVector::Dist(GeneratedRoot->GetComponentLocation(), Expected) > ToleranceCm)
		{
			OutError = FString::Printf(TEXT("Root[%d] location/mobility mismatch, expected=%s actual=%s"),
				Index, *Expected.ToString(), IsValid(GeneratedRoot) ? *GeneratedRoot->GetComponentLocation().ToString() : TEXT("missing"));
			return false;
		}
	}
	return true;
}

bool AFactoryEquipmentIndicator::IsGeneratedGeometryHidden() const
{
	if (GeometryRoots.IsEmpty() || RenderedPrimitives.IsEmpty())
	{
		return false;
	}
	for (const TWeakObjectPtr<USceneComponent>& Component : GeometryRoots)
	{
		if (!Component.IsValid() || Component->IsVisible())
		{
			return false;
		}
	}
	for (const TWeakObjectPtr<UPrimitiveComponent>& Primitive : RenderedPrimitives)
	{
		if (!Primitive.IsValid() || Primitive->IsVisible())
		{
			return false;
		}
	}
	return true;
}

void AFactoryEquipmentIndicator::FaceCamera(const FVector& CameraLocation)
{
	if (IsValid(Label))
	{
		Label->SetWorldRotation((CameraLocation - Label->GetComponentLocation()).Rotation());
	}
}
