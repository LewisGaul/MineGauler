## TLDR: Normal workflow
1. Change to base branch: `git checkout <branch>`
2. Update: `git pull --rebase`
3. Create new branch: `git checkout -b <new branch>`
4. (Make changes)
5. Commit changes (assuming no new files created): `git commit -am "<msg>"`
6. Push changes to remote: `git push`
   * If on a new branch you will need to set the name of the 'upstream' (remote) branch with:  
   `git push -u origin <branch name>`
7. Create a pull request on [github.com](https://github.com) (and add me as a reviewer)
8. Make any changes I request and push them to the remote
9. When the changes are accepted, the branch can be merged down and deleted

## Update a branch
* Update a branch from the remote:  
`git pull --rebase`
* To merge in changes from a different branch:
  * Change to the other branch, e.g. `git checkout v4/dev`
  * Update: `git pull --rebase`
  * Change back: `git checkout v4/feature-gui-wip`
  * Merge (hopefully works automatically!): `git merge v4/dev`
  
## Create a branch
* Change to the branch you want to use as the base, e.g.  
`git checkout v4/feature-gui-wip`
* Update the base branch (see above)
* Create and change to new branch, e.g.  
`git checkout -b v4/feature-FG-face`

## Commit changes
* Add (stage) certain files to be committed
  * Specific files or directories: `git add <path>`
  * All tracked files: `git add -u`
  * All files including untracked: `git add .`
  * Interactive adding: `git add -i`
* Commit staged changes, e.g.  
`git commit -m "Tidy up set_cell() method"`
  * To automatically add all changes in tracked files use the `-a` option, e.g.  
  `git commit -am "<msg>"`

## Push changes
* Push all committed changes on the branch:  
`git push`
  * If on a new branch you will need to set the name of the 'upstream' (remote) branch with:  
      `git push -u origin <branch name>`
      
