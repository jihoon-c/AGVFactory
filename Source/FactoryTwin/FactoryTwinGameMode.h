#pragma once

#include "CoreMinimal.h"
#include "GameFramework/GameModeBase.h"
#include "FactoryTwinGameMode.generated.h"

class AFactoryTwinDirector;

UCLASS()
class FACTORYTWIN_API AFactoryTwinGameMode : public AGameModeBase
{
	GENERATED_BODY()

public:
	AFactoryTwinGameMode();
	virtual void StartPlay() override;
	AFactoryTwinDirector* GetDirector() const { return Director; }

private:
	UPROPERTY(Transient)
	TObjectPtr<AFactoryTwinDirector> Director;
};
