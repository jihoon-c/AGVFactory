#include "FactoryTwinHUD.h"

#include "FactoryEventReplayComponent.h"
#include "FactoryTwinDirector.h"
#include "FactoryTwinGameMode.h"
#include "Engine/Canvas.h"
#include "Engine/World.h"

void AFactoryTwinHUD::DrawHUD()
{
	Super::DrawHUD();
	const AFactoryTwinGameMode* Mode = GetWorld() ? GetWorld()->GetAuthGameMode<AFactoryTwinGameMode>() : nullptr;
	const AFactoryTwinDirector* Director = Mode ? Mode->GetDirector() : nullptr;
	if (!Director)
	{
		return;
	}
	DrawText(TEXT("FACTORY TWIN  |  USD Stage + file-based JSONL replay"), FLinearColor::White, 30, 32, nullptr, 1.25f);
	DrawText(Director->GetDisplayStatus(), FLinearColor::Yellow, 30, 65);
	if (const UFactoryEventReplayComponent* Replay = Director->GetReplay())
	{
		const FString Playback = FString::Printf(TEXT("Stage ID bindings: %d / 5  |  Events: %d / %d  |  Virtual time: %.1fs  |  %s"),
			Director->GetLoadedBindings(), Replay->GetCursor(), Replay->GetEventCount(),
			Replay->GetCurrentTimeMs() / 1000.0, Replay->IsPlaying() ? TEXT("PLAY") : TEXT("PAUSE"));
		DrawText(Playback, FLinearColor::White, 30, 95);
	}
	DrawText(TEXT("SPACE: Play/Pause    R: Reset    1: One AGV    2: Two AGVs"), FLinearColor::White, 30, 125);
	DrawText(TEXT("Idle: gray  Busy: green  Down: red  Moving: blue | input is virtual factory data"), FLinearColor::White, 30, 155);
	if (Canvas && Director->GetLoadedBindings() == 5)
	{
		const float Left = FMath::Max(10.0f, Canvas->ClipX - 270.0f);
		DrawRect(FLinearColor(0.015f, 0.025f, 0.04f, 0.88f), Left - 12.0f, 18.0f, 265.0f, 203.0f);
		DrawText(TEXT("EQUIPMENT  |  VIRTUAL STATE"), FLinearColor::White, Left, 26.0f);
		static const TCHAR* EquipmentIds[] = { TEXT("M01"), TEXT("M02"), TEXT("QC01"), TEXT("AGV01"), TEXT("AGV02") };
		for (int32 Index = 0; Index < UE_ARRAY_COUNT(EquipmentIds); ++Index)
		{
			const FString State = Director->GetEquipmentState(EquipmentIds[Index]);
			const FLinearColor Color = State == TEXT("Down") ? FLinearColor::Red :
				State == TEXT("Busy") ? FLinearColor::Green : State == TEXT("Moving") ? FLinearColor::Blue :
				FLinearColor(0.65f, 0.65f, 0.65f);
			const float Y = 61.0f + Index * 30.0f;
			DrawRect(Color, Left, Y, 22.0f, 21.0f);
			DrawText(FString(EquipmentIds[Index]) + TEXT("  ") + State, FLinearColor::White, Left + 32.0f, Y);
		}
	}
}
