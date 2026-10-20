#pragma once

#include "CoreMinimal.h"
#include "FactoryEquipmentRegistrySubsystem.h"
#include "GameFramework/Actor.h"
#include "FactoryTwinDirector.generated.h"

class AUsdStageActor;
class ACameraActor;
class UFactoryEquipmentRegistrySubsystem;
class UFactoryEventReplayComponent;

UCLASS()
class FACTORYTWIN_API AFactoryTwinDirector : public AActor
{
	GENERATED_BODY()

public:
	AFactoryTwinDirector();
	virtual void BeginPlay() override;
	virtual void Tick(float DeltaSeconds) override;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "FactoryTwin|Files")
	FString UsdRootRelative = TEXT("usd/factory_scene.usda");

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "FactoryTwin|Files")
	FString ManifestRelative = TEXT("data/equipment_manifest.json");

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "FactoryTwin|Files")
	FString ReplayRelative = TEXT("Reports/run_agv_2_seed42.jsonl");

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "FactoryTwin|Replay")
	bool bAutoPlayWhenReady = true;

	UFUNCTION(BlueprintCallable, CallInEditor, Category = "FactoryTwin")
	void ReloadFiles();

	UFUNCTION(BlueprintCallable, Category = "FactoryTwin")
	void ToggleReplay();

	UFUNCTION(BlueprintCallable, Category = "FactoryTwin")
	void ResetReplay();

	UFUNCTION(BlueprintCallable, Category = "FactoryTwin")
	void LoadAgvOne();

	UFUNCTION(BlueprintCallable, Category = "FactoryTwin")
	void LoadAgvTwo();

	FString GetDisplayStatus() const;
	int32 GetLoadedBindings() const;
	FString GetEquipmentState(const FString& EquipmentId) const;
	UFactoryEventReplayComponent* GetReplay() const { return Replay; }

private:
	UPROPERTY(VisibleAnywhere)
	TObjectPtr<UFactoryEventReplayComponent> Replay;

	UPROPERTY(Transient)
	TObjectPtr<AUsdStageActor> StageActor;

	UPROPERTY(Transient)
	TObjectPtr<ACameraActor> ViewCamera;

	TArray<FFactoryManifestRecord> ManifestRecords;
	bool bBound = false;
	bool bWaitingForStage = false;
	bool bSmokeMode = false;
	bool bVisualQaMode = false;
	bool bVisualQaAgvOne = false;
	bool bNegativeQaMode = false;
	bool bSmokeReported = false;
	int32 VisualQaCaptureIndex = 0;
	bool bVisualQaWaitingForImage = false;
	FString VisualQaImagePath;
	FString VisualQaTag;
	float VisualQaFinishDelay = 0.0f;
	float VisualQaWarmupSeconds = 0.0f;
	float RetryClockSeconds = 0.0f;
	int32 RetryAttempts = 0;
	FString Status = TEXT("Not initialized");

	UFactoryEquipmentRegistrySubsystem* Registry() const;
	void TryBindStage();
	void ReloadJsonl();
	void FrameCamera();
	void TickVisualQa(float DeltaSeconds);
	void RunNegativeQa();
	void SetError(const FString& Error);
	static FString FullProjectPath(const FString& RelativePath);
};
