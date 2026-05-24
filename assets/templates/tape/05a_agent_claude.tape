# SCENE 7a: Claude Code reading the shared vault
# Duration: ~5s · part of split: VO [0:53–1:10] "One vault. Every agent you use."
# Output dimensions match the other two agent tapes for grid compositing.

Output "05a_agent_claude.mp4"
Output "05a_agent_claude.gif"

Set Theme '{ "name": "{{project_name}}", "background": "{{palette_bg}}", "foreground": "{{palette_fg}}", "cursor": "{{palette_accent}}", "selection": "{{palette_rule}}", "black": "{{palette_bg}}", "red": "{{mem_decision}}", "green": "{{mem_skill}}", "yellow": "{{palette_accent}}", "blue": "{{mem_constraint}}", "magenta": "{{mem_episodic}}", "cyan": "{{mem_preference}}", "white": "{{palette_fg}}", "brightBlack": "{{palette_fg_faint}}", "brightRed": "{{mem_correction}}", "brightGreen": "{{mem_skill}}", "brightYellow": "{{mem_fact}}", "brightBlue": "{{mem_constraint}}", "brightMagenta": "{{mem_episodic}}", "brightCyan": "{{mem_preference}}", "brightWhite": "#ffffff" }'

Set FontFamily "{{font_mono}}"
Set FontSize 18
Set Width 700
Set Height 680
Set Padding 50

Hide
Type "bash display.sh agent:0"
Enter
Show
Sleep 5s
