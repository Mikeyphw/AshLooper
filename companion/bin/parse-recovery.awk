# Read *new* AshReXcue log bytes. Attribution requires a recovery-stage marker.
# Output: kind TAB id TAB recovery-stage. No eval or shell interpolation.
{
  message = $0
  if (message !~ /^\[[^]]+\] >\[/ || message !~ /\]<$/) next
  sub(/^\[[^]]+\] >\[/, "", message)
  sub(/\]<$/, "", message)

  if (index(message, "NEW BOOT") > 0) { recovery = 0; stage = ""; next }
  if (index(message, "NUKING all scripts") > 0) {
    recovery = 1; stage = "nuclear"; next
  }
  if (index(message, "Threshold reached - disabling new modules") == 1) {
    recovery = 1; stage = "targeted"; next
  }
  if (message == "Lockdown Mode Activated") {
    recovery = 1
    if (stage != "nuclear") stage = "lockdown"
    next
  }
  if (!recovery) next
  if (index(message, "Disabled module: ") == 1) {
    sub(/^Disabled module: /, "", message)
    if (message != "") printf "module\t%s\t%s\n", message, stage
  } else if (index(message, "Module disabled: ") == 1) {
    sub(/^Module disabled: /, "", message)
    sub(/^\/data\/adb\/modules\//, "", message)
    if (message != "") printf "module\t%s\t%s\n", message, stage
  } else if (index(message, "Disabled script: ") == 1) {
    sub(/^Disabled script: /, "", message)
    sub(/ ->.*$/, "", message)
    sub(/^\/data\/adb\/service\.d\//, "", message)
    if (message ~ /^[A-Za-z0-9_.@+-]+\.sh$/)
      printf "script\tsvc:%s\t%s\n", message, stage
  }
}
