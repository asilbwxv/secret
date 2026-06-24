function gw {
    local gradle_wrapper="./gradlew"
    local current_dir="$(pwd)"
    local git_dir="$(git rev-parse --show-toplevel 2>/dev/null)"
 
    if [ -n "$git_dir" ]; then
        if [ -x "$git_dir/$gradle_wrapper" ]; then
            cd "$git_dir" || return
            "$gradle_wrapper" "$@"
            cd "$current_dir" || return
        else
            echo "Error: $gradle_wrapper not found in the root of the Git repository."
        fi
    else
        echo "Error: Not inside a Git repository."
    fi
}
