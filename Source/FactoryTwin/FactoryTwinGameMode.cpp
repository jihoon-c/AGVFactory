#include "FactoryTwinGameMode.h"

#include "FactoryTwinDirector.h"
#include "FactoryTwinHUD.h"
#include "Engine/World.h"

AFactoryTwinGameMode::AFactoryTwinGameMode()
{
	HUDClass = AFactoryTwinHUD::StaticClass();
}

void AFactoryTwinGameMode::StartPlay()
{
	Super::StartPlay();
	if (GetWorld())
	{
		Director = GetWorld()->SpawnActor<AFactoryTwinDirector>();
	}
}
