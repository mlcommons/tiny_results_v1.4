# MLPerf™ Tiny v1.1

## Submit Results
Before Submitting your code and results to this GitHub page, you must run
submission_checker.py and email the output csv to the Chairs (please include
*both* csaba@mlcommons.org and jeremy@mlcommons.org).

Before 1 pm PT on May 19th 2023, you must:
* run the submission_checker.py on a clean copy of your working directory
* check the outcome, optinally solve WARNINGS
* Email the output of submission_checker.py *and* the CSV file generated
to the chairs (csaba@mlcommons.org and jeremy@mlcommons.org)

From here you have two options, one which MUST be done before 1:30 pm PT on May 19th 2023,
- GitHub based submission as done in previous versions (see below)
- encrypted submission (see below)
These two options only differ in the last step of the guide below.
## Submission HOWTO
### Clone the MLPerf™ Tiny v1.1 submission tree

Clone the submission tree e.g. under your home directory:

```bash
$ export SUBMISSION_ROOT=$HOME/submissions_tiny_v1_1
$ git clone git@github.com:mlcommons/submissions_tiny_v1.1.git $SUBMISSION_ROOT
$ cd $SUBMISSION_ROOT
```

### Create a branch

We recommend creating a new branch for every logically connected group of
results e.g. all results from your System-Under-Test (SUT) or only relating to
a particular benchmark. Prefix your branch name with your organization's name.
Feel free to include the SUT name, implementation name, benchmark name, etc.

For example:

```bash
$ git checkout master && git pull
$ git checkout -b dividiti-closed-aws-g4dn.4xlarge-openvino
```

Populate your branch according to the [MLPerf Tiny Directory Structure](https://github.com/mlcommons/submissions_tiny_v1.1/blob/master/directory_structure.adoc).

You can inspect your changes:

```bash
$ git status
On branch dividiti-closed-aws-g4dn.4xlarge-openvino
Untracked files:
  (use "git add <file>..." to include in what will be committed)

        closed/dividiti/code/
        closed/dividiti/results/
        closed/dividiti/systems/

nothing added to commit but untracked files present (use "git add" to track)
```

and make intermediate commits as usual:

```bash
$ git add closed/dividiti
$ git commit -m "Dump repo:mlperf-closed-aws-g4dn.4xlarge-openvino."
```

### Submit your repo
As stated before, here you have two options
- submit a pull request with all of the required components, before 1:30 pm PT
- create an encrypted archive of your whole repository, including the .git folder, and send it before 1:30 pm PT

#### Option 1 (preferred) GitHub based submission
##### Push the changes to GitHub

Once you are happy with the tree structure, you can push the changes:

```bash
$ git push

fatal: The current branch dividiti-closed-aws-g4dn.4xlarge-openvino has no upstream branch.
To push the current branch and set the remote as upstream, use

    git push --set-upstream origin dividiti-closed-aws-g4dn.4xlarge-openvino
```

Do exactly as suggested:

```bash
$ git push --set-upstream origin dividiti-closed-aws-g4dn.4xlarge-openvino
```

##### Create a pull request

If you now go to https://github.com/mlcommons/submissions_tiny_v1.1, you should see a notification
about your branch being recently pushed and can immediately create a pull request (PR).
You can also select your branch from the dropdown menu under `<> Code`. (Aren't you happy you prefixed your branch's name with the submitter's name?)

As usual, you can continue committing to the branch until the PR is merged, with any changes
being reflected in the PR.

#### Option 2 (new, less tested) encrypted submission

- check that your working directory is clean, i.e. the same as what is committed
Use `git diff` and `git status` as explained above

- fix differences either by committing or by removing files

- create an (optionally encrypted) archive (tgz preferred) of your whole working directory,
including the .git folder

- generate the sha256 of your archive
`sha256sum mycompany_archive_to_send.tgz > checksum`

- email the archive to csaba@mlcommons.org, optionally also to jeremy@mlcommons.org

- in a *separate email*, send the sha256 checksum and the password to csaba@mlcommons.org

Note: it is important that the second email is a separate one without the big attachment, so that it goes through even if
there are problems with the attachment.

Note: Overall there are 3 emails in this case
- 1st: with output of submission_checker.py
- 2nd: with archive
- 3rd: with sha256 and password

