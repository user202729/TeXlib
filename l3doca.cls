% just like l3doc but with some customizations
\RequirePackage{fvextra}
\LoadClass{l3doc}
\fvset{breaklines=true,gobble=0,tabsize=4,frame=single,numbers=left,numbersep=3pt}
\AtBeginDocument{\DeleteShortVerb\"}  % https://tex.stackexchange.com/a/650966/250119
\MakeOuterQuote{"}

