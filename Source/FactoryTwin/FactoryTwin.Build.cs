using UnrealBuildTool;

public class FactoryTwin : ModuleRules
{
	public FactoryTwin(ReadOnlyTargetRules Target) : base(Target)
	{
		PCHUsage = PCHUsageMode.UseExplicitOrSharedPCHs;
		PublicDependencyModuleNames.AddRange(new string[] { "Core", "CoreUObject", "Engine", "InputCore", "Json", "USDStage" });
		PrivateDependencyModuleNames.Add("UnrealUSDWrapper");
	}
}
