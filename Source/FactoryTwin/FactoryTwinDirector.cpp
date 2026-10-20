#include "FactoryTwinDirector.h"

#include "FactoryEquipmentIndicator.h"
#include "FactoryEquipmentRegistrySubsystem.h"
#include "FactoryEventReplayComponent.h"

#include "Camera/CameraActor.h"
#include "Components/PrimitiveComponent.h"
#include "Components/InputComponent.h"
#include "Components/SceneComponent.h"
#include "Engine/World.h"
#include "EngineUtils.h"
#include "GameFramework/PlayerController.h"
#include "HAL/FileManager.h"
#include "InputCoreTypes.h"
#include "Kismet/GameplayStatics.h"
#include "Misc/Paths.h"
#include "Misc/CommandLine.h"
#include "Misc/Parse.h"
#include "UnrealClient.h"
#include "USDStageActor.h"
#include "UsdWrappers/SdfPath.h"
#include "UsdWrappers/UsdStage.h"
#include "UsdWrappers/UsdPrim.h"
#include "UsdWrappers/UsdAttribute.h"

namespace
{
	bool ReadFactoryTwinPathArg(const TCHAR* Name, FString& OutValue)
	{
		const FString Prefix = FString(TEXT("-")) + Name + TEXT("=");
		const TCHAR* Cursor = FCommandLine::Get();
		FString Token;
		while (FParse::Token(Cursor, Token, false))
		{
			if (Token.StartsWith(Prefix, ESearchCase::IgnoreCase))
			{
				OutValue = Token.RightChop(Prefix.Len());
				return !OutValue.IsEmpty();
			}
		}
		return false;
	}

	// USDImporter may create components for an Xform, an inner Mesh, or a collapsed
	// reference. Resolve only components whose real source prim is in this specific
	// Geometry subtree. Never bind an unrelated collapsed /World component.
	void CollectGeneratedVisuals(const AUsdStageActor& StageActor, const UE::FUsdPrim& RootPrim,
		const FString& GeometryPath, TArray<USceneComponent*>& OutComponents, int32& VisitedCount)
	{
		if (!RootPrim || ++VisitedCount > 4096)
		{
			return;
		}
		const FString PrimPath = RootPrim.GetPrimPath().GetString();
		if (PrimPath != GeometryPath && !PrimPath.StartsWith(GeometryPath + TEXT("/")))
		{
			return;
		}
		if (USceneComponent* Candidate = StageActor.GetGeneratedComponent(PrimPath))
		{
			const FString SourcePrimPath = StageActor.GetSourcePrimPath(Candidate);
			if ((SourcePrimPath == PrimPath || SourcePrimPath == GeometryPath ||
				SourcePrimPath.StartsWith(GeometryPath + TEXT("/"))) &&
				!OutComponents.Contains(Candidate))
			{
				OutComponents.Add(Candidate);
			}
		}
		for (const UE::FUsdPrim& Child : RootPrim.GetFilteredChildren(true))
		{
			CollectGeneratedVisuals(StageActor, Child, GeometryPath, OutComponents, VisitedCount);
		}
	}
}

AFactoryTwinDirector::AFactoryTwinDirector()
{
	PrimaryActorTick.bCanEverTick = true;
	Replay = CreateDefaultSubobject<UFactoryEventReplayComponent>(TEXT("EventReplay"));
}

FString AFactoryTwinDirector::FullProjectPath(const FString& RelativePath)
{
	return FPaths::ConvertRelativePathToFull(FPaths::ProjectDir(), RelativePath);
}

UFactoryEquipmentRegistrySubsystem* AFactoryTwinDirector::Registry() const
{
	return GetWorld() ? GetWorld()->GetSubsystem<UFactoryEquipmentRegistrySubsystem>() : nullptr;
}

void AFactoryTwinDirector::BeginPlay()
{
	Super::BeginPlay();
	bSmokeMode = FParse::Param(FCommandLine::Get(), TEXT("FactoryTwinSmoke"));
	bVisualQaMode = FParse::Param(FCommandLine::Get(), TEXT("FactoryTwinVisualQA"));
	bVisualQaAgvOne = FParse::Param(FCommandLine::Get(), TEXT("FactoryTwinVisualQAAgvOne"));
	bVisualQaMode = bVisualQaMode || bVisualQaAgvOne;
	bNegativeQaMode = FParse::Param(FCommandLine::Get(), TEXT("FactoryTwinNegativeQA"));
	// Read exact whitespace-delimited tokens: paths must retain USD/JSON file extensions.
	ReadFactoryTwinPathArg(TEXT("FactoryTwinUsdRoot"), UsdRootRelative);
	ReadFactoryTwinPathArg(TEXT("FactoryTwinManifest"), ManifestRelative);
	ReadFactoryTwinPathArg(TEXT("FactoryTwinReplay"), ReplayRelative);
	UE_LOG(LogTemp, Display, TEXT("FACTORYTWIN_QA_ARGS_RAW: %s"), FCommandLine::Get());
	FParse::Value(FCommandLine::Get(), TEXT("FactoryTwinVisualQATag="), VisualQaTag);
	if (!VisualQaTag.IsEmpty())
	{
		FString SafeTag;
		for (const TCHAR C : VisualQaTag)
		{
			if (FChar::IsAlnum(C) || C == TCHAR('-') || C == TCHAR('_'))
			{
				SafeTag.AppendChar(C);
			}
		}
		VisualQaTag = SafeTag.Left(32);
	}
	if (bVisualQaAgvOne)
	{
		ReplayRelative = TEXT("Reports/run_agv_1_seed42.jsonl");
	}
	if (bVisualQaMode)
	{
		Replay->PlaybackSpeed = 100.0;
		bAutoPlayWhenReady = true;
		UE_LOG(LogTemp, Display, TEXT("FACTORYTWIN_VISUAL_QA_START: D3D viewport screenshot capture requested"));
	}
	if (bSmokeMode)
	{
		Replay->PlaybackSpeed = 3600.0;
		bAutoPlayWhenReady = true;
	}
	if (APlayerController* PC = UGameplayStatics::GetPlayerController(this, 0))
	{
		EnableInput(PC);
		if (InputComponent)
		{
			InputComponent->BindKey(EKeys::SpaceBar, IE_Pressed, this, &AFactoryTwinDirector::ToggleReplay);
			InputComponent->BindKey(EKeys::R, IE_Pressed, this, &AFactoryTwinDirector::ResetReplay);
			InputComponent->BindKey(EKeys::One, IE_Pressed, this, &AFactoryTwinDirector::LoadAgvOne);
			InputComponent->BindKey(EKeys::Two, IE_Pressed, this, &AFactoryTwinDirector::LoadAgvTwo);
		}
	}
	ReloadFiles();
}

void AFactoryTwinDirector::SetError(const FString& Error)
{
	Status = TEXT("ERROR: ") + Error;
	UE_LOG(LogTemp, Error, TEXT("FactoryTwin: %s"), *Status);
	if (bSmokeMode && !bSmokeReported)
	{
		bSmokeReported = true;
		UE_LOG(LogTemp, Error, TEXT("FACTORYTWIN_SMOKE_FAIL: %s"), *Error);
		FPlatformMisc::RequestExit(false);
	}
	else if (bVisualQaMode && !bSmokeReported)
	{
		bSmokeReported = true;
		UE_LOG(LogTemp, Error, TEXT("FACTORYTWIN_VISUAL_QA_FAIL: %s"), *Error);
		FPlatformMisc::RequestExit(false);
	}
}

void AFactoryTwinDirector::ReloadFiles()
{
	check(IsInGameThread());
	if (!GetWorld() || !Registry())
	{
		SetError(TEXT("No world or equipment registry"));
		return;
	}
	Replay->ResetReplay(Registry());
	Registry()->ClearRegistry();
	for (TActorIterator<AFactoryEquipmentIndicator> It(GetWorld()); It; ++It)
	{
		It->Destroy();
	}
	if (IsValid(StageActor))
	{
		StageActor->Destroy();
		StageActor = nullptr;
	}
	ManifestRecords.Empty();
	bBound = false;
	bWaitingForStage = false;
	RetryAttempts = 0;
	RetryClockSeconds = 0;
	const FString UsdFile = FullProjectPath(UsdRootRelative);
	UE_LOG(LogTemp, Display, TEXT("FACTORYTWIN_STAGE_SELECTION: usd=%s manifest=%s"), *UsdRootRelative, *ManifestRelative);
	if (!FPaths::FileExists(UsdFile))
	{
		SetError(FString::Printf(TEXT("USD root missing: %s (Worker A output pending)"), *UsdFile));
		return;
	}
	FString Error;
	// Preview USD stages are allowed for renderer QA, but the manifest continues
	// to declare the immutable contract entrypoint usd/factory_scene.usda.
	const FString ManifestContractRoot = FullProjectPath(TEXT("usd/factory_scene.usda"));
	if (!Registry()->ParseManifest(FullProjectPath(ManifestRelative), ManifestContractRoot, ManifestRecords, Error))
	{
		SetError(Error);
		return;
	}
	StageActor = GetWorld()->SpawnActor<AUsdStageActor>(FVector::ZeroVector, FRotator::ZeroRotator);
	if (!IsValid(StageActor))
	{
		SetError(TEXT("Failed to spawn USD Stage Actor"));
		return;
	}
	StageActor->bUsePrimKindsForCollapsing = false;
	StageActor->SetRootLayer(UsdFile);
	StageActor->SetStageState(EUsdStageState::OpenedAndLoaded);
	bWaitingForStage = true;
	Status = FString::Printf(TEXT("Loading USD Stage: %s"), *UsdFile);
	TryBindStage();
}

void AFactoryTwinDirector::TryBindStage()
{
	if (!bWaitingForStage || !IsValid(StageActor) || !Registry())
	{
		return;
	}
	// Avoid interpreting an async USD translation's temporarily missing components as a valid binding.
	TArray<USceneComponent*> Components;
	TArray<FVector> PrimLocationsCm;
	TArray<TArray<USceneComponent*>> GeometryComponents;
	for (const FFactoryManifestRecord& Record : ManifestRecords)
	{
		const UE::FUsdPrim Prim = StageActor->GetUsdStage().GetPrimAtPath(UE::FSdfPath(*Record.PrimPath));
		const UE::FUsdAttribute IdAttribute = Prim ? Prim.GetAttribute(TEXT("twin:equipmentId")) : UE::FUsdAttribute();
		FString UsdId;
		if (!Prim || !IdAttribute || !IdAttribute.Get(UsdId) || UsdId != Record.EquipmentId)
		{
			bWaitingForStage = false;
			SetError(FString::Printf(TEXT("USD custom attribute ID mismatch: %s (USD: '%s')"), *Record.EquipmentId, *UsdId));
			return;
		}
		FVector3d PositionMeters = FVector3d::ZeroVector;
		const UE::FUsdAttribute PositionAttribute = Prim.GetAttribute(TEXT("xformOp:translate"));
		if (!PositionAttribute || !PositionAttribute.Get(PositionMeters))
		{
			bWaitingForStage = false;
			SetError(FString::Printf(TEXT("USD prim missing translate in meters: %s"), *Record.PrimPath));
			return;
		}
		PrimLocationsCm.Add(FVector(PositionMeters) * 100.0);
		USceneComponent* Component = StageActor->GetGeneratedComponent(Record.PrimPath);
		if (IsValid(Component))
		{
			const FString ActualPrimPath = StageActor->GetSourcePrimPath(Component);
			if (ActualPrimPath != Record.PrimPath)
			{
				UE_LOG(LogTemp, Warning, TEXT("FactoryTwin: %s generated under %s; using explicit USD prim/manifest overlay"),
					*Record.PrimPath, *ActualPrimPath);
				Component = nullptr;
			}
		}
		Components.Add(Component);
		const FString GeometryPath = Record.PrimPath + TEXT("/Geometry");
		const UE::FUsdPrim GeometryPrim = StageActor->GetUsdStage().GetPrimAtPath(UE::FSdfPath(*GeometryPath));
		if (!GeometryPrim)
		{
			bWaitingForStage = false;
			SetError(FString::Printf(TEXT("USD visual anchor missing: %s"), *GeometryPath));
			return;
		}
		TArray<USceneComponent*> ImportedGeometry;
		int32 VisitedCount = 0;
		CollectGeneratedVisuals(*StageActor, GeometryPrim, GeometryPath, ImportedGeometry, VisitedCount);
		bool bHasActualMesh = false;
		for (USceneComponent* Candidate : ImportedGeometry)
		{
			bHasActualMesh |= Candidate->IsA<UPrimitiveComponent>();
		}
		if (!bHasActualMesh)
		{
			// USD Stage translation may still be running when we first bind. A broken
			// prefab/reference must become a clear error instead of invisible success.
			if (++RetryAttempts > 80)
			{
				bWaitingForStage = false;
				SetError(FString::Printf(TEXT("No generated mesh in USD visual subtree: %s (visited %d USD prims)"),
					*GeometryPath, VisitedCount));
			}
			return;
		}
		UE_LOG(LogTemp, Display, TEXT("FACTORYTWIN_VISUAL_BIND: %s anchor=%s imported_components=%d"),
			*Record.EquipmentId, *GeometryPath, ImportedGeometry.Num());
		GeometryComponents.Add(MoveTemp(ImportedGeometry));
	}
	TArray<AFactoryEquipmentIndicator*> Spawned;
	FString Error;
	for (int32 Index = 0; Index < ManifestRecords.Num(); ++Index)
	{
		const FFactoryManifestRecord& Record = ManifestRecords[Index];
		AFactoryEquipmentIndicator* Indicator = GetWorld()->SpawnActor<AFactoryEquipmentIndicator>();
		if (!IsValid(Indicator) || !Registry()->RegisterBinding(Record, Indicator, Components[Index], Error))
		{
			for (AFactoryEquipmentIndicator* Created : Spawned) { Created->Destroy(); }
			if (Indicator) { Indicator->Destroy(); }
			Registry()->ClearRegistry();
			bWaitingForStage = false;
			SetError(Error.IsEmpty() ? TEXT("Could not spawn UE equipment indicator") : Error);
			return;
		}
		Indicator->InitializeVisuals(Record.EquipmentId, Record.Kind, PrimLocationsCm[Index],
			Components[Index], GeometryComponents[Index]);
		Spawned.Add(Indicator);
	}
	bBound = true;
	bWaitingForStage = false;
	for (int32 Index = 0; Index < ManifestRecords.Num(); ++Index)
	{
		Registry()->SetWaypoint(ManifestRecords[Index].EquipmentId, PrimLocationsCm[Index]);
	}
	static const TCHAR* Locations[] = { TEXT("INBOUND"), TEXT("OUTBOUND") };
	for (const TCHAR* Location : Locations)
	{
		const FString PrimPath = FString::Printf(TEXT("/World/Factory/Locations/%s"), Location);
		const UE::FUsdPrim Prim = StageActor->GetUsdStage().GetPrimAtPath(UE::FSdfPath(*PrimPath));
		FVector3d PositionMeters = FVector3d::ZeroVector;
		if (Prim && Prim.GetAttribute(TEXT("xformOp:translate")).Get(PositionMeters))
		{
			Registry()->SetWaypoint(Location, FVector(PositionMeters) * 100.0);
		}
	}
	Status = FString::Printf(TEXT("USD loaded; %d manifest equipment IDs bound"), Registry()->NumBindings());
	UE_LOG(LogTemp, Display, TEXT("FactoryTwin: %s"), *Status);
	for (const TCHAR* GeometryPath : { TEXT("/World/Factory/Locations/INBOUND/Geometry") })
	{
		USceneComponent* Generated = StageActor->GetGeneratedComponent(GeometryPath);
		if (UPrimitiveComponent* Mesh = Cast<UPrimitiveComponent>(Generated))
		{
			UE_LOG(LogTemp, Display, TEXT("FACTORYTWIN_USD_RENDER_BOUNDS: %s source=%s box_size_cm=%s"),
				GeometryPath, *StageActor->GetSourcePrimPath(Mesh), *(Mesh->Bounds.BoxExtent * 2.0).ToString());
		}
		else
		{
			UE_LOG(LogTemp, Warning, TEXT("FACTORYTWIN_USD_RENDER_BOUNDS_UNAVAILABLE: %s (USD scene prim exists; direct generated geometry component not resolved)"), GeometryPath);
		}
	}
	if (const AFactoryEquipmentIndicator* M01 = Registry()->FindEquipment(TEXT("M01")))
	{
		const FBox Bounds = M01->GetGeometryBounds();
		if (Bounds.IsValid)
		{
			UE_LOG(LogTemp, Display, TEXT("FACTORYTWIN_USD_RENDER_BOUNDS: /World/Factory/Equipment/M01/Geometry source=validated-subtree box_size_cm=%s"),
				*Bounds.GetSize().ToString());
		}
	}
	for (const FFactoryManifestRecord& Record : ManifestRecords)
	{
		const AFactoryEquipmentIndicator* Bound = Registry()->FindEquipment(Record.EquipmentId);
		UE_LOG(LogTemp, Display, TEXT("FACTORYTWIN_MODEL_GEOMETRY: id=%s rendered_primitives=%d roots=%d dimensions_cm=%s"),
			*Record.EquipmentId, Bound ? Bound->GetVisiblePrimitiveCount() : 0,
			Bound ? Bound->GetGeometryRootCount() : 0,
			Bound ? *Bound->GetGeometryBounds().GetSize().ToString() : TEXT("missing"));
	}
	FrameCamera();
	if (bNegativeQaMode)
	{
		RunNegativeQa();
		return;
	}
	ReloadJsonl();
}

void AFactoryTwinDirector::RunNegativeQa()
{
	struct FNegativeCase
	{
		const TCHAR* File;
		bool bManifest;
	};
	static const FNegativeCase Cases[] = {
		{ TEXT("manifest_duplicate_id.json"), true },
		{ TEXT("manifest_wrong_kind.json"), true },
		{ TEXT("replay_malformed.jsonl"), false },
		{ TEXT("replay_unknown_id.jsonl"), false },
		{ TEXT("replay_out_of_order.jsonl"), false },
		{ TEXT("replay_duplicate_event_id.jsonl"), false }
	};
	int32 Passed = 0;
	for (const FNegativeCase& Test : Cases)
	{
		const FString Fixture = FullProjectPath(FString(TEXT("Docs/UEQAInputs/")) + Test.File);
		FString Error;
		TArray<FFactoryManifestRecord> Ignored;
		const bool bAccepted = Test.bManifest ?
			Registry()->ParseManifest(Fixture, FullProjectPath(UsdRootRelative), Ignored, Error) :
			Replay->LoadJsonl(Fixture, Registry(), Error);
		if (bAccepted || Error.IsEmpty())
		{
			UE_LOG(LogTemp, Error, TEXT("FACTORYTWIN_NEGATIVE_QA_FAIL: %s unexpectedly accepted or has no rejection detail"), Test.File);
			FPlatformMisc::RequestExit(false);
			return;
		}
		++Passed;
		UE_LOG(LogTemp, Display, TEXT("FACTORYTWIN_NEGATIVE_QA_CASE_PASS: %s rejected: %s"), Test.File, *Error);
	}
	UE_LOG(LogTemp, Display, TEXT("FACTORYTWIN_NEGATIVE_QA_PASS: %d invalid manifest/replay inputs rejected with actual UE parsers"), Passed);
	FPlatformMisc::RequestExit(false);
}

void AFactoryTwinDirector::FrameCamera()
{
	FBox Bounds(ForceInit);
	for (const FFactoryManifestRecord& Record : ManifestRecords)
	{
		FVector Position;
		if (Registry() && Registry()->FindWaypoint(Record.EquipmentId, Position))
		{
			Bounds += Position;
		}
	}
	if (!Bounds.IsValid)
	{
		return;
	}
	const FVector Center = Bounds.GetCenter();
	const double Extent = FMath::Max(700.0, Bounds.GetExtent().GetMax() * 3.5);
	const FVector Eye = Center + FVector(-Extent, -Extent, Extent * 0.8);
	if (!IsValid(ViewCamera))
	{
		ViewCamera = GetWorld()->SpawnActor<ACameraActor>();
	}
	if (IsValid(ViewCamera))
	{
		ViewCamera->SetActorLocationAndRotation(Eye, (Center - Eye).Rotation());
		for (TActorIterator<AFactoryEquipmentIndicator> It(GetWorld()); It; ++It)
		{
			It->FaceCamera(Eye);
		}
		if (APlayerController* PC = UGameplayStatics::GetPlayerController(this, 0))
		{
			PC->SetViewTarget(ViewCamera);
		}
	}
}

void AFactoryTwinDirector::ReloadJsonl()
{
	if (!bBound || !Registry())
	{
		SetError(TEXT("Cannot replay before USD/manifest binding"));
		return;
	}
	FString Error;
	FString JsonlPath = FullProjectPath(ReplayRelative);
	if (!FPaths::FileExists(JsonlPath))
	{
		// Worker B currently publishes raw results in the shared job-stack workspace.
		const FString SharedPath = FullProjectPath(TEXT("../FactoryTwinUE_JobStack_OneWeek/") + ReplayRelative);
		if (FPaths::FileExists(SharedPath))
		{
			JsonlPath = SharedPath;
		}
	}
	if (!Replay->LoadJsonl(JsonlPath, Registry(), Error))
	{
		SetError(Error);
		return;
	}
	Status = FString::Printf(TEXT("Replay ready: %d ordered events, %s"), Replay->GetEventCount(), *ReplayRelative);
	UE_LOG(LogTemp, Display, TEXT("FactoryTwin: %s"), *Status);
	Replay->SetPlaying(bAutoPlayWhenReady && !bVisualQaMode);
}

void AFactoryTwinDirector::ToggleReplay()
{
	if (Replay->IsLoaded())
	{
		Replay->SetPlaying(!Replay->IsPlaying());
	}
}

void AFactoryTwinDirector::ResetReplay()
{
	Replay->ResetReplay(Registry());
}

void AFactoryTwinDirector::LoadAgvOne()
{
	ReplayRelative = TEXT("Reports/run_agv_1_seed42.jsonl");
	ReloadJsonl();
}

void AFactoryTwinDirector::LoadAgvTwo()
{
	ReplayRelative = TEXT("Reports/run_agv_2_seed42.jsonl");
	ReloadJsonl();
}

void AFactoryTwinDirector::Tick(float DeltaSeconds)
{
	Super::Tick(DeltaSeconds);
	if (bWaitingForStage)
	{
		RetryClockSeconds += DeltaSeconds;
		if (RetryClockSeconds >= 0.25f)
		{
			RetryClockSeconds = 0;
			TryBindStage();
		}
	}
	if (Replay->IsPlaying())
	{
		Replay->AdvanceReplay(DeltaSeconds, Registry());
		if (!Replay->GetLastError().IsEmpty())
		{
			SetError(Replay->GetLastError());
		}
	}
	if (bVisualQaMode && bBound && Replay->IsLoaded() && !bSmokeReported)
	{
		TickVisualQa(DeltaSeconds);
	}
	if (bSmokeMode && !bSmokeReported && bBound && Replay->IsLoaded() &&
		!Replay->IsPlaying() && Replay->GetCursor() == Replay->GetEventCount())
	{
		bSmokeReported = true;
		UE_LOG(LogTemp, Display, TEXT("FACTORYTWIN_SMOKE_PASS: USD stage bound %d IDs, replayed %d events through %lldms"),
			Registry() ? Registry()->NumBindings() : 0, Replay->GetEventCount(), Replay->GetCurrentTimeMs());
		FPlatformMisc::RequestExit(false);
	}
}

void AFactoryTwinDirector::TickVisualQa(float DeltaSeconds)
{
	VisualQaWarmupSeconds += DeltaSeconds;
	if (VisualQaWarmupSeconds < 1.5f)
	{
		return;
	}
	static const int64 CaptureTimesMs[] = { 2000, 25000, 220000, 270000 };
	static const TCHAR* CaptureLabels[] = { TEXT("idle"), TEXT("busy"), TEXT("down"), TEXT("repaired") };
	static const TCHAR* ExpectedM01States[] = { TEXT("Idle"), TEXT("Busy"), TEXT("Down"), TEXT("Busy") };
	constexpr int32 CaptureCount = UE_ARRAY_COUNT(CaptureTimesMs);
	if (bVisualQaWaitingForImage)
	{
		if (FPaths::FileExists(VisualQaImagePath))
		{
			UE_LOG(LogTemp, Display, TEXT("FACTORYTWIN_VISUAL_QA_CAPTURED: %s"), *VisualQaImagePath);
			bVisualQaWaitingForImage = false;
			++VisualQaCaptureIndex;
		}
		return;
	}
	if (VisualQaCaptureIndex >= CaptureCount)
	{
		VisualQaFinishDelay += DeltaSeconds;
		if (VisualQaFinishDelay >= 0.5f)
		{
			bSmokeReported = true;
			UE_LOG(LogTemp, Display, TEXT("FACTORYTWIN_VISUAL_QA_PASS: %d rendered screenshots verified on disk; five USD bindings"), CaptureCount);
			FPlatformMisc::RequestExit(false);
		}
		return;
	}
	if (Replay->GetCurrentTimeMs() < CaptureTimesMs[VisualQaCaptureIndex])
	{
		// Advance only in the QA harness; shader compilation or first-frame stalls must not skip the Idle sample.
		const double RemainingVirtualSeconds = static_cast<double>(CaptureTimesMs[VisualQaCaptureIndex] - Replay->GetCurrentTimeMs()) / 1000.0;
		Replay->SetPlaying(true);
		Replay->AdvanceReplay((RemainingVirtualSeconds + 0.001) / Replay->PlaybackSpeed, Registry());
		Replay->SetPlaying(false);
	}
	if (FScreenshotRequest::IsScreenshotRequested())
	{
		return;
	}
	const AFactoryEquipmentIndicator* M01 = Registry()->FindEquipment(TEXT("M01"));
	const AFactoryEquipmentIndicator* M02 = Registry()->FindEquipment(TEXT("M02"));
	const AFactoryEquipmentIndicator* AGV01 = Registry()->FindEquipment(TEXT("AGV01"));
	const AFactoryEquipmentIndicator* AGV02 = Registry()->FindEquipment(TEXT("AGV02"));
	for (const TCHAR* AgvId : { TEXT("AGV01"), TEXT("AGV02") })
	{
		if (bVisualQaAgvOne && FString(AgvId) == TEXT("AGV02"))
		{
			continue;
		}
		const AFactoryEquipmentIndicator* Indicator = Registry()->FindEquipment(AgvId);
		FString GeometryError;
		if (!IsValid(Indicator) || !Indicator->VerifyGeometryPlacement(1.0f, GeometryError))
		{
			SetError(FString::Printf(TEXT("AGV replay geometry mismatch or static component: %s, %s"), AgvId, *GeometryError));
			bSmokeReported = true;
			UE_LOG(LogTemp, Error, TEXT("FACTORYTWIN_VISUAL_QA_FAIL: %s"), *Status);
			FPlatformMisc::RequestExit(false);
			return;
		}
		UE_LOG(LogTemp, Display, TEXT("FACTORYTWIN_VISUAL_QA_AGV_GEOMETRY: %s generated_roots=%d primitives=%d waypoint_center_cm=%s"),
			AgvId, Indicator->GetGeometryRootCount(), Indicator->GetVisiblePrimitiveCount(),
			*(Indicator->GetActorLocation() - FVector(0, 0, 140)).ToString());
	}
	if (bVisualQaAgvOne && IsValid(AGV02))
	{
		if (!AGV02->IsHidden() || !AGV02->IsGeneratedGeometryHidden())
		{
			SetError(TEXT("AGV=1 must hide AGV02 indicator and actual USD-generated geometry"));
			bSmokeReported = true;
			UE_LOG(LogTemp, Error, TEXT("FACTORYTWIN_VISUAL_QA_FAIL: AGV02 remains visible in AGV=1 scenario"));
			FPlatformMisc::RequestExit(false);
			return;
		}
		UE_LOG(LogTemp, Display, TEXT("FACTORYTWIN_VISUAL_QA_AGV_ONE: AGV02 indicator hidden, Stage-generated geometry invisible"));
	}
	if (!IsValid(M01) || !IsValid(M02) || !IsValid(AGV01) || !IsValid(AGV02) ||
		M01->GetState() != ExpectedM01States[VisualQaCaptureIndex])
	{
		SetError(FString::Printf(TEXT("Visual QA snapshot expected M01=%s at virtual %lldms, actual=%s"),
			ExpectedM01States[VisualQaCaptureIndex], Replay->GetCurrentTimeMs(), IsValid(M01) ? *M01->GetState() : TEXT("missing")));
		bSmokeReported = true;
		UE_LOG(LogTemp, Error, TEXT("FACTORYTWIN_VISUAL_QA_FAIL: %s"), *Status);
		FPlatformMisc::RequestExit(false);
		return;
	}
	UE_LOG(LogTemp, Display, TEXT("FACTORYTWIN_VISUAL_QA_STATE: t_ms=%lld M01=%s M02=%s AGV01=%s pos_cm=%s AGV02=%s pos_cm=%s"),
		Replay->GetCurrentTimeMs(), *M01->GetState(), *M02->GetState(), *AGV01->GetState(), *AGV01->GetActorLocation().ToString(),
		*AGV02->GetState(), *AGV02->GetActorLocation().ToString());
	if (!GEngine || !GEngine->GameViewport || !GEngine->GameViewport->Viewport)
	{
		SetError(TEXT("Visual QA requires an actual game viewport"));
		bSmokeReported = true;
		UE_LOG(LogTemp, Error, TEXT("FACTORYTWIN_VISUAL_QA_FAIL: viewport unavailable"));
		FPlatformMisc::RequestExit(false);
		return;
	}
	const FString ImageDirectory = FullProjectPath(TEXT("Docs/UnrealCaptures"));
	IFileManager::Get().MakeDirectory(*ImageDirectory, true);
	VisualQaImagePath = ImageDirectory / FString::Printf(TEXT("FactoryTwin_%s%s%s_%s.png"),
		VisualQaTag.IsEmpty() ? TEXT("") : *VisualQaTag, VisualQaTag.IsEmpty() ? TEXT("") : TEXT("_"),
		bVisualQaAgvOne ? TEXT("agv1") : TEXT("agv2"), CaptureLabels[VisualQaCaptureIndex]);
	FScreenshotRequest::RequestScreenshot(VisualQaImagePath, true, false);
	bVisualQaWaitingForImage = true;
	UE_LOG(LogTemp, Display, TEXT("FACTORYTWIN_VISUAL_QA_REQUESTED: %s"), *VisualQaImagePath);
}

FString AFactoryTwinDirector::GetDisplayStatus() const
{
	return Status;
}

int32 AFactoryTwinDirector::GetLoadedBindings() const
{
	return Registry() ? Registry()->NumBindings() : 0;
}

FString AFactoryTwinDirector::GetEquipmentState(const FString& EquipmentId) const
{
	if (const UFactoryEquipmentRegistrySubsystem* EquipmentRegistry = Registry())
	{
		if (const AFactoryEquipmentIndicator* Indicator = EquipmentRegistry->FindEquipment(EquipmentId))
		{
			return Indicator->IsHidden() ? TEXT("Inactive") : Indicator->GetState();
		}
	}
	return TEXT("Unbound");
}
