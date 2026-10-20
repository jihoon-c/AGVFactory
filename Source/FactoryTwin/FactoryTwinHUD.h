#pragma once

#include "CoreMinimal.h"
#include "GameFramework/HUD.h"
#include "FactoryTwinHUD.generated.h"

UCLASS()
class FACTORYTWIN_API AFactoryTwinHUD : public AHUD
{
	GENERATED_BODY()

public:
	virtual void DrawHUD() override;
};
