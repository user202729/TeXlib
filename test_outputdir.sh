#!/bin/bash
cd /tmp/
rm -r outputdir-test-folder 2>/dev/null
mkdir outputdir-test-folder
cd outputdir-test-folder

mkdir aa

cat > a.tex << 'eof'
\documentclass{article}
\usepackage{outputdir}
\outputdirstopifundefined
\typeout{^^J^^J>>>>>\meaning\outputdir^^J^^J}
\begin{document}
\end{document}
eof

set -x

rm a.fls a.aux aa/a.fls aa/a.aux

pdflatex a.tex </dev/null | grep '>>>>>' | diff --color=always - <(true)
pdflatex -recorder a.tex </dev/null | grep '>>>>>' | diff --color=always - <(echo '>>>>>macro:->/tmp/outputdir-test-folder/')
pdflatex a.tex </dev/null | grep '>>>>>' | diff --color=always - <(echo '>>>>>macro:->/tmp/outputdir-test-folder/')  # after one run of recorder, following run can use
pdflatex -output-directory=aa/ a.tex </dev/null | grep '>>>>>' | diff --color=always - <(echo '>>>>>macro:->/tmp/outputdir-test-folder/')  # unfortunately this one is [INCORRECT]
pdflatex -shell-escape -output-directory=aa/ a.tex </dev/null | grep '>>>>>' | diff --color=always - <(true)  # it successfully determine that something is wrong

rm a.fls a.aux aa/a.fls aa/a.aux

lualatex a.tex </dev/null | grep '>>>>>' | diff --color=always - <(echo '>>>>>macro:->./')  # sometimes it's relative, but it's okay
lualatex -output-directory=aa/ a.tex </dev/null | grep '>>>>>' | diff --color=always - <(echo '>>>>>macro:->aa//')  # sometimes the / is doubled but it's also okay
lualatex -output-directory=aa a.tex </dev/null | grep '>>>>>' | diff --color=always - <(echo '>>>>>macro:->aa/')

cat > a.tex << 'eof'
\documentclass{article}
\usepackage[default=bb]{outputdir}
\typeout{^^J^^J>>>>>\meaning\outputdir^^J^^J}
\begin{document}
\end{document}
eof

rm a.fls a.aux aa/a.fls aa/a.aux

pdflatex -output-directory=aa/ a.tex </dev/null | grep '>>>>>' | diff --color=always - <(echo '>>>>>macro:->bb')  # if suggested should use. In this case cannot determine something is [INCORRECT]
pdflatex -shell-escape -output-directory=aa/ a.tex </dev/null | grep '>>>>>' | diff --color=always - <(echo '>>>>>undefined')  # shell-escape can detect something is wrong, but cannot fix it
pdflatex -recorder -shell-escape -output-directory=aa/ a.tex </dev/null | grep '>>>>>' | diff --color=always - <(echo '>>>>>macro:->aa//')  # recorder can fix it

# ======== give correct suggestion here
cat > a.tex << 'eof'
\documentclass{article}
\usepackage[default=aa]{outputdir}
\typeout{^^J^^J>>>>>\meaning\outputdir^^J^^J}
\begin{document}
\end{document}
eof

rm a.fls a.aux aa/a.fls aa/a.aux

pdflatex -shell-escape -output-directory=aa/ a.tex </dev/null | grep '>>>>>' | diff --color=always - <(echo '>>>>>macro:->aa')  # shell-escape should confirm
