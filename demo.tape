# VHS Demo Script for Curlens
# Run with: vhs demo.tape

Output demo.gif
Set FontSize 16
Set Width 900
Set Height 500
Set Theme "Dracula"
Set Padding 20

# Show the search command
Type "curlens -d 'python script to pause glue jobs'"
Sleep 500ms
Enter
Sleep 3s

# Select option 1
Type "1"
Enter
Sleep 2s

# Cancel before cursor agent takes over (for demo purposes)
Ctrl+C
Sleep 3s
