#!/usr/bin/env python3
"""
Persona Selector Utility
Easily switch between different voice personas for the LiveKit agent.
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from personas import PERSONAS, get_available_personas

def show_personas():
    """Display all available personas with details."""
    print("\n🎭 Available Voice Personas:")
    print("=" * 60)
    
    for name, persona in PERSONAS.items():
        print(f"\n👤 {persona.name.upper()} ({name})")
        print(f"   Age: {persona.age}, Nationality: {persona.nationality}")
        print(f"   Voice: {persona.voice_id} ({persona.speaking_style} style)")
        print(f"   Personality: {persona.personality_core[:80]}...")
        print(f"   Traits: {', '.join(persona.traits[:4])}")
        print(f"   Interests: {', '.join(persona.interests[:4])}")

def set_persona(persona_name):
    """Update the agent.py file to use the specified persona."""
    if persona_name not in PERSONAS:
        print(f"❌ Persona '{persona_name}' not found!")
        print(f"Available personas: {', '.join(get_available_personas())}")
        return False
    
    # Read current agent.py
    agent_file = "agent.py"
    with open(agent_file, 'r') as f:
        content = f.read()
    
    # Find and replace the SELECTED_PERSONA line
    import re
    pattern = r'SELECTED_PERSONA = DEFAULT_PERSONA'
    replacement = f'SELECTED_PERSONA = "{persona_name}"  # Changed from DEFAULT_PERSONA'
    
    if re.search(pattern, content):
        new_content = re.sub(pattern, replacement, content)
    else:
        # Try alternative pattern with quotes
        pattern = r'SELECTED_PERSONA = "[^"]*"'
        replacement = f'SELECTED_PERSONA = "{persona_name}"'
        if re.search(pattern, content):
            new_content = re.sub(pattern, replacement, content)
        else:
            print("❌ Could not find SELECTED_PERSONA in agent.py")
            return False
    
    # Write back to file
    with open(agent_file, 'w') as f:
        f.write(new_content)
    
    persona = PERSONAS[persona_name]
    print(f"✅ Persona updated to: {persona.name}")
    print(f"🎤 Voice: {persona.voice_id} ({persona.speaking_style} style)")
    print(f"💭 Personality: {persona.personality_core[:60]}...")
    print("\n🔄 Restart the agent to apply changes!")
    return True

def main():
    if len(sys.argv) < 2:
        show_personas()
        print(f"\n📋 Usage:")
        print(f"   python {sys.argv[0]} <persona_name>   # Set persona")
        print(f"   python {sys.argv[0]} list             # Show all personas")
        print(f"\n💡 Example: python {sys.argv[0]} alex")
        return
    
    command = sys.argv[1].lower()
    
    if command == "list":
        show_personas()
    elif command in get_available_personas():
        set_persona(command)
    else:
        print(f"❌ Unknown persona or command: {command}")
        print(f"Available personas: {', '.join(get_available_personas())}")
        print(f"Available commands: list")

if __name__ == "__main__":
    main()