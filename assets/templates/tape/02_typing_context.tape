# SCENE 2: User typing same context for the Nth time
# Duration: ~10s · VO: [0:04–0:12] "You explain your stack. Your conventions..."

Output "02_typing_context.mp4"
Output "02_typing_context.gif"

Set Theme '{ "name": "{{project_name}}", "background": "{{palette_bg}}", "foreground": "{{palette_fg}}", "cursor": "{{palette_accent}}", "selection": "{{palette_rule}}", "black": "{{palette_bg}}", "red": "{{mem_decision}}", "green": "{{mem_skill}}", "yellow": "{{palette_accent}}", "blue": "{{mem_constraint}}", "magenta": "{{mem_episodic}}", "cyan": "{{mem_preference}}", "white": "{{palette_fg}}", "brightBlack": "{{palette_fg_faint}}", "brightRed": "{{mem_correction}}", "brightGreen": "{{mem_skill}}", "brightYellow": "{{mem_fact}}", "brightBlue": "{{mem_constraint}}", "brightMagenta": "{{mem_episodic}}", "brightCyan": "{{mem_preference}}", "brightWhite": "#ffffff" }'

Set FontFamily "{{font_mono}}"
Set FontSize 22
Set Width 1280
Set Height 720
Set Padding 80
Set TypingSpeed 45ms

Hide
Type "bash display.sh input"
Enter
Show

Sleep 800ms
Type "postgres + drizzle, pnpm workspaces, vitest, no db mocks, composition over inheritance — and stop suggesting express, we moved to hono."
Sleep 2s
