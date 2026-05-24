# SCENE 3: Frustrated dev — "we discussed this yesterday"
# Duration: ~8s · VO: [0:13–0:17] "Agents are brilliant. And amnesiac."

Output "03_amnesia.mp4"
Output "03_amnesia.gif"

Set Theme '{ "name": "{{project_name}}", "background": "{{palette_bg}}", "foreground": "{{palette_fg}}", "cursor": "{{palette_accent}}", "selection": "{{palette_rule}}", "black": "{{palette_bg}}", "red": "{{mem_decision}}", "green": "{{mem_skill}}", "yellow": "{{palette_accent}}", "blue": "{{mem_constraint}}", "magenta": "{{mem_episodic}}", "cyan": "{{mem_preference}}", "white": "{{palette_fg}}", "brightBlack": "{{palette_fg_faint}}", "brightRed": "{{mem_correction}}", "brightGreen": "{{mem_skill}}", "brightYellow": "{{mem_fact}}", "brightBlue": "{{mem_constraint}}", "brightMagenta": "{{mem_episodic}}", "brightCyan": "{{mem_preference}}", "brightWhite": "#ffffff" }'

Set FontFamily "{{font_mono}}"
Set FontSize 22
Set Width 1280
Set Height 720
Set Padding 80
Set TypingSpeed 60ms

Hide
Type "bash display.sh amnesia"
Enter
Show

Sleep 1500ms
Type "we discussed this yesterday."
Sleep 3s
