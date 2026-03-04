// Copyright Epic Games, Inc. All Rights Reserved.

using UnrealBuildTool;

public class UnrealMCP : ModuleRules
{
	public UnrealMCP(ReadOnlyTargetRules Target) : base(Target)
	{
		PCHUsage = ModuleRules.PCHUsageMode.UseExplicitOrSharedPCHs;
		
		PublicDefinitions.Add("UNREALMCP_EXPORTS=1");

		PublicIncludePaths.AddRange(
			new string[] {
				System.IO.Path.Combine(ModuleDirectory, "Public"),
				System.IO.Path.Combine(ModuleDirectory, "Public/Commands"),
				System.IO.Path.Combine(ModuleDirectory, "Public/Commands/BlueprintGraph"),
				System.IO.Path.Combine(ModuleDirectory, "Public/Commands/BlueprintGraph/Nodes")
			}
		);

		PrivateIncludePaths.AddRange(
			new string[] {
				System.IO.Path.Combine(ModuleDirectory, "Private"),
				System.IO.Path.Combine(ModuleDirectory, "Private/Commands"),
				System.IO.Path.Combine(ModuleDirectory, "Private/Commands/BlueprintGraph"),
				System.IO.Path.Combine(ModuleDirectory, "Private/Commands/BlueprintGraph/Nodes")
			}
		);
		
		PublicDependencyModuleNames.AddRange(
			new string[]
			{
				"Core",
				"CoreUObject",
				"Engine",
				"InputCore",
				"Networking",
				"Sockets",
				"HTTP",
				"Json",
				"JsonUtilities",
				"DeveloperSettings",
				"PhysicsCore",
				"UnrealEd",           // For Blueprint editing
				"BlueprintGraph",     // For K2Node classes (F15-F22)
				"KismetCompiler",     // For Blueprint compilation (F15-F22)
				"AIModule",
				"NavigationSystem",
				
				// *** Phase 1: GameplayTasks Integration ***
				"GameplayTasks",      // For async AI task execution
				"GameplayTags",       // For tag-based logic
				
				// *** Phase 2: Mass Entity System (Core modules only) ***
				"StructUtils",        // Required for Mass Entity
				"MassEntity",         // Core ECS framework
				"MassCommon",         // Common utilities
				"MassSpawner",        // Entity spawning
				"MassRepresentation", // Visual representation
				"MassMovement",       // Movement processing
				"MassNavigation",     // Navigation integration
				"MassSimulation",     // Simulation framework
				"MassActors",         // Actor integration
				"MassGameplayDebug",  // Debug tools
				"MassAIBehavior",     // AI behaviors for Mass
				"MassSignals",        // Signal system
				"MassSmartObjects",   // Smart object integration
				"ZoneGraph",          // Navigation graphs
				"ZoneGraphAnnotations", // Graph annotations
				
				// *** Phase 2: StateTree (Modern AI) ***
				"StateTreeModule",    // Core StateTree
				"GameplayStateTreeModule", // Component and common tasks
				"StateTreeEditorModule" // Editor support
			}
		);
		
		PrivateDependencyModuleNames.AddRange(
			new string[]
			{
				"EditorScriptingUtilities",
				"EditorSubsystem",
				"Slate",
				"SlateCore",
				"Kismet",
				"Projects",
				"AssetRegistry",
				"PythonScriptPlugin"
			}
		);
		
		if (Target.bBuildEditor == true)
		{
			PrivateDependencyModuleNames.AddRange(
				new string[]
				{
					"PropertyEditor",      // For property editing
					"ToolMenus",           // For editor UI
					"BlueprintEditorLibrary" // For Blueprint utilities
				}
			);
		}
		
		DynamicallyLoadedModuleNames.AddRange(
			new string[]
			{
				// ... add any modules that your module loads dynamically here ...
			}
		);
	}
} 