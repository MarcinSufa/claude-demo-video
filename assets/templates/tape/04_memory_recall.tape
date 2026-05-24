# SCENE 4: New session, ExoVault auto-loads context (3-phase: empty → loading → loaded)
# Duration: ~10s · VO: [1:11–1:21] "New session. No re-introduction needed."

Output "04_memory_recall.mp4"
Output "04_memory_recall.gif"

Set Theme '{ "name": "{{project_name}}", "background": "{{palette_bg}}", "foreground": "{{palette_fg}}", "cursor": "{{palette_accent}}", "selection": "{{palette_rule}}", "black": "{{palette_bg}}", "red": "{{mem_decision}}", "green": "{{mem_skill}}", "yellow": "{{palette_accent}}", "blue": "{{mem_constraint}}", "magenta": "{{mem_episodic}}", "cyan": "{{mem_preference}}", "white": "{{palette_fg}}", "brightBlack": "{{palette_fg_faint}}", "brightRed": "{{mem_correction}}", "brightGreen": "{{mem_skill}}", "brightYellow": "{{mem_fact}}", "brightBlue": "{{mem_constraint}}", "brightMagenta": "{{mem_episodic}}", "brightCyan": "{{mem_preference}}", "brightWhite": "#ffffff" }'

Set FontFamily "{{font_mono}}"
Set FontSize 22
Set Width 1280
Set Height 720
Set Padding 80
Set TypingSpeed 45ms

Hide
Type "bash display.sh recall"
Enter
Show

# Phases 1-3 self-time inside display.sh (1.5s empty + 1.2s loading + reveal)
Sleep 4s
Type "continue where we left off."
Sleep 3s
