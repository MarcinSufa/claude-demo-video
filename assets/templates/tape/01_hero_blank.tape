# SCENE 1: Hero shot — empty Claude Code prompt, cursor blinks
# Duration: ~6s · VO: [0:00–0:04] "Every session starts the same way."

Output "01_hero_blank.mp4"
Output "01_hero_blank.gif"

Set Theme '{ "name": "{{project_name}}", "background": "{{palette_bg}}", "foreground": "{{palette_fg}}", "cursor": "{{palette_accent}}", "selection": "{{palette_rule}}", "black": "{{palette_bg}}", "red": "{{mem_decision}}", "green": "{{mem_skill}}", "yellow": "{{palette_accent}}", "blue": "{{mem_constraint}}", "magenta": "{{mem_episodic}}", "cyan": "{{mem_preference}}", "white": "{{palette_fg}}", "brightBlack": "{{palette_fg_faint}}", "brightRed": "{{mem_correction}}", "brightGreen": "{{mem_skill}}", "brightYellow": "{{mem_fact}}", "brightBlue": "{{mem_constraint}}", "brightMagenta": "{{mem_episodic}}", "brightCyan": "{{mem_preference}}", "brightWhite": "#ffffff" }'

Set FontFamily "{{font_mono}}"
Set FontSize 22
Set Width 1280
Set Height 720
Set Padding 80

Hide
Type "bash display.sh hero"
Enter
Show
Sleep 5s
