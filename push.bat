@echo off
echo ========================================
echo Pushing latest Goober updates to GitHub...
echo ========================================
git add .
git commit -m "Auto-update goober script"
git push
echo ========================================
echo Push complete!
echo ========================================
pause