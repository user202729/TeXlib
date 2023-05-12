#let sequence=$a b$.body.func()
#let alignpoint=$&$.body.func()
#let mathstyle=$upright(A)$.body.func()
#let space=$a b$.body.children.at(1).func()
#set page(width: 100cm)
// we do the above to avoid pdftotext removing spaces when they coincide with newlines

#{
assert(repr(alignpoint)=="alignpoint")
assert(repr(mathstyle)=="mathstyle")
assert(repr(sequence)=="sequence")
assert(repr(space)=="space")
}

#let variant_to_latex_lookup=(
"sans": "\\mathsf",
"frak": "\\mathfrak",
"mono": "\\mathtt",
"bb": "\\mathbb",
"cal": "\\mathcal",
)

#let displaystyle=0
#let textstyle=1
#let scriptstyle=2
#let scriptscriptstyle=3
// type enum STYLE = {displaystyle, textstyle, scriptstyle, scriptscriptstyle}

#let nextstyle(x) = { // style → style
  assert(0<=x and x<=3)
  calc.min(x+1, scriptscriptstyle)
}
#let nextscriptstyle(x) = { // style → style
  calc.max(scriptstyle, nextstyle(x))
}
#let defaultstyleheight(x) = {if x>=scriptstyle{0.55} else {1}}

// type struct TEX = {body: str, height: float, align: bool, linebreak: bool}

#let cat(style, ..a) = { // style, ⟨str|tex⟩... -> tex
  let result=(
    body: "",
    height: defaultstyleheight(style),
    align: false,
    linebreak: false,
  )
  for x in a.pos() {
    if type(x)=="string" {
      x=(
        body: x, height: defaultstyleheight(style), align: false, linebreak: false
      )
    }else{
      assert(type(x)=="dictionary", message: "unexpected type "+type(x))
    }
    result=(
      body: result.body+x.body,
      height: calc.max(result.height, x.height),
      align: result.align or x.align,
      linebreak: result.linebreak or x.linebreak,
    )
  }
  result
}

#let vcat(..a) = { // ⟨str|tex⟩... -> tex
  let result=(
    body: "",
    height: 0,
    align: false,
    linebreak: false,
  )
  for x in a.pos() {
    if type(x)=="string" {
      x=(
        body: x, height: 0, align: false, linebreak: false
      )
    }else{
      assert(type(x)=="dictionary", message: "unexpected type "+type(x))
    }
    result=(
      body: result.body+x.body,
      height: result.height+x.height,
      align: result.align or x.align,
      linebreak: result.linebreak or x.linebreak,
    )
  }
  result
}

#let setheight(x, height) = { // tex, float -> tex
  x.height=height
  x
}
#let adddelimsize(x, delimsize) = { // tex, str[Literal["\\big", ...]] -> tex
  if x.body=="" { x.body="." }
  x.body=delimsize+x.body
  x
}

#let delimtomatenv(x) = { // content → (str, str)
  let delim="(" // assume this is the default, not necessarily true
  if x.has("delim"){ delim=x.delim }
  if      delim=="("{ ("\\begin{pmatrix}", "\\end{pmatrix}") }
  else if delim=="["{ ("\\begin{bmatrix}", "\\end{bmatrix}") }
  else if delim=="{"{ ("\\begin{Bmatrix}", "\\end{Bmatrix}") }
  else if delim=="|"{ ("\\begin{vmatrix}", "\\end{vmatrix}") }
  else if delim=="||"{ ("\\begin{Vmatrix}", "\\end{Vmatrix}") }
  else if delim==none{ ("\\begin{matrix}", "\\end{matrix}") }
  else { ("\\text{unknown delim " + repr(delim) + "}\\begin{matrix}", "\\end{matrix}") }
}

// content, style → tex
#let equation_body_to_latex(x, style, spacebefore: false, spaceafter: false) = {cat(style, ..{
  if x.func()==sequence{
    let l=x.children
    for (i, y) in l.enumerate(){
      (equation_body_to_latex(y, style,
        spacebefore: if i>0{l.at(i - 1).func()==space} else {spacebefore},
        spaceafter: if i < l.len()-1{l.at(i+1).func()==space} else {spaceafter},
      ),)
    }
  }else if x.func()==math.lr{
    assert(x.body.func()==sequence)
    if x.body.children.len()<=2{
      for (i, y) in x.body.children.enumerate(){
        (equation_body_to_latex(y, style),)
      }
    }else{
      let tmp=cat(style, ..{
        for (i, y) in x.body.children.enumerate(){
          if i>0 and x.body.children.len()-1>i{
            (equation_body_to_latex(y, style,
              spacebefore: x.body.children.at(i - 1).func()==space,
              spaceafter: x.body.children.at(i+1).func()==space,
            ),)
          }
        }
      })
      let bracketstyle={
        if tmp.height<=1.3 {""}
        else if tmp.height<=1.4 {"\\big"}
        else if tmp.height<=1.7 {"\\Big"}
        else if tmp.height<=2.1 {"\\bigg"}
        else {"\\Bigg"}
      }
      (adddelimsize(equation_body_to_latex(x.body.children.at(0), style), bracketstyle),
      tmp,
      adddelimsize(equation_body_to_latex(x.body.children.at(-1), style), bracketstyle))
    }
  }else if x.func()==math.vec{
    let (startenv, stopenv)=delimtomatenv(x)
    (vcat(..{
      (startenv,)
      for (i, v) in x.children.enumerate(){
        if i>0{ ("\\\\",) }
        (equation_body_to_latex(v, style),)
      }
      (stopenv,)
    }),)
  }else if x.func()==math.cases{
    (vcat(..{
      ("\\begin{cases}",)
      for (i, row) in x.children.enumerate(){
        if i>0{ ("\\\\",) }
        (equation_body_to_latex(row, style),)
      }
    ("\\end{cases}",)
    }),)
  }else if x.func()==math.mat{
    let (startenv, stopenv)=delimtomatenv(x)
    (vcat(..{
      (startenv,)
      for (i, row) in x.rows.enumerate(){
        if i>0{ ("\\\\",) }
        (cat(style, ..{
          for (j, v) in row.enumerate(){
            if j>0{ ("&",) }
            (equation_body_to_latex(v, style),)
          }
        }),)
      }
    (stopenv,)
    }),)
  }else if x.func()==math.op{
    ({
      if x.limits{
        "\\operatorname*{"
      }else{
        "\\operatorname{"
      }
      x.text
      "}"
    },)
  }else if x.func()==space{
    ()
    //"\\ "
  }else if x.func()==h{
    ("\\hspace{" + repr(x.amount) + "}"
    ,)  // a bit ugly with repr but okay
  }else if x.func()==math.equation{
    // just flatten it
    (equation_body_to_latex(x.body, style),)
  }else if x.func()==text{
    let wrap_in_text = {
      if x.text.match(regex("^[0-9.]+$"))!=none {
        false
      }else{
        x.text.clusters().len()>1
      }
    }
    let content={
      if x.text.starts-with("!!"){
        x.text.slice(2)
      }else{
        if wrap_in_text { "\\typstmathinputtext{" }
        x.text
          .replace("{", "\\{")
          .replace("}", "\\}")
        if wrap_in_text { "}" }
      }
    }
    if style==displaystyle and (content=="∑" or content=="∏" or content=="∫"){
      content=setheight(cat(style, content), 1.4)
    }

    if content=="|" and spacebefore and spaceafter { ("\\mid ",) }
    else if content=="‖" and spacebefore and spaceafter { ("\\parallel ",) }
    else {
      // currently Typst code such as `x "is natural"` will make the TeX code omit the space before the quote.
      // there seems to be no good solution? Just stick with typing `x" is natural"` instead
      //if spacebefore and (content=="|" or content=="‖" or wrap_in_text){ ("\\mathrel{}",) }
      (content,)
      //if spaceafter and (content=="|" or content=="‖" or wrap_in_text){ ("\\mathrel{}",) }
    }
  }else if x.func()==math.root{
    ("\\sqrt",)
    if x.has("index"){
      ("[{",)
      let tmp=equation_body_to_latex(x.index, nextscriptstyle(style))
      tmp.height+=0.7*defaultstyleheight(style)
      (tmp,)
      ("}]",)
    }
    ("{",)
    let tmp=equation_body_to_latex(x.radicand, style)
    tmp.height+=0.3
    (tmp,)
    ("}",)
  }else if x.func()==math.attach{
    (equation_body_to_latex(x.base, style),)
    if x.has("top"){
      ("^{",
      equation_body_to_latex(x.top, nextscriptstyle(style)),
      "}")
    }
    if x.has("bottom"){
      ("_{",
      equation_body_to_latex(x.bottom, nextscriptstyle(style)),
      "}")
    }
  }else if x.func()==math.frac{
    let tmp=equation_body_to_latex(x.num, nextstyle(style))
    let tmp2=equation_body_to_latex(x.denom, nextstyle(style))
    let tmp3=cat(style, "\\frac{", tmp, "}{", tmp2, "}")
    (setheight(tmp3, tmp.height+tmp2.height),)
  }else if x.func()==math.binom{
    let tmp=equation_body_to_latex(x.upper, nextstyle(style))
    let tmp2=equation_body_to_latex(x.lower, nextstyle(style))
    let tmp3=cat(style, "\\binom{", tmp, "}{", tmp2, "}")
    (setheight(tmp3, tmp.height+tmp2.height),)
  }else if x.func()==mathstyle{
    if x.has("bold"){
      assert(not x.has("italic"))
      assert(not x.has("variant"))
      assert(x.bold)
      ("\\mathbf{",
      equation_body_to_latex(x.body, style),
      "}")
    }else if x.has("italic"){
      assert(not x.has("variant"))
      if x.italic{
        ("\\mathit{",
        equation_body_to_latex(x.body, style),
        "}")
      }else{
        ("\\mathrm{",
        equation_body_to_latex(x.body, style),
        "}")
      }
    }else{
      (variant_to_latex_lookup.at(x.variant),
      "{",
      equation_body_to_latex(x.body, style),
      "}")
    }
  }else if x.func()==alignpoint{
    let tmp=cat(style, "&")
    tmp.align=true
    (tmp,)
  }else if x.func()==linebreak{
    let tmp=cat(style, "\\\\")
    tmp.linebreak=true
    (tmp,)
  }else{
    ("\\text{(unknown func " + repr(x.func()) + ")}",)
  }
})}

// content[$...$] → tex
#let equation_to_latex(x) = {
  assert(x.func()==math.equation)
  if x.block {
    let body=equation_body_to_latex(x.body, displaystyle)
    if body.align or body.linebreak{
      "\\begin{align*}\\typstmathinputnormcat " + body.body + "\\end{align*}"
    } else {
      "\\[\\typstmathinputnormcat " + body.body + "\\]"
    }
  } else {
    "\\(\\typstmathinputnormcat " + equation_body_to_latex(x.body, textstyle).body + "\\)" // for usage from TeX don't use active `$` which recursively call the original function
  }
}






#{
let asserte(x, y) = assert(x==y, message: repr(x)+" ≠ "+repr(y))
asserte( equation_body_to_latex($a$.body, textstyle).height, 1 )
asserte( equation_body_to_latex($sqrt(a)$.body, textstyle).height, 1.3 )
asserte( equation_body_to_latex($sqrt(sqrt(a))$.body, textstyle).height, 1.6 )

asserte( equation_body_to_latex($a/b$.body, displaystyle).height, 2 )
asserte( equation_body_to_latex($a/b$.body, textstyle).height, 1.1 )

asserte( equation_body_to_latex($∑$.body, textstyle).height, 1 )
asserte( equation_body_to_latex($∑$.body, displaystyle).height, 1.4 )

asserte( equation_body_to_latex($vec(1, 2)$.body, displaystyle).height, 2 )
asserte( equation_body_to_latex($mat(1, 2; 3, 4; 5, 6)$.body, displaystyle).height, 3 )
asserte( equation_body_to_latex($mat(1, 2/3; 3, 4; 5, 6)$.body, displaystyle).height, 4 )

}

//#import "/home/user202729/TeX/typstmathinput-template.typ": equation_to_latex

#let a =($ 
binom(1, 2)
    vec(1, 2, delim: "[")
    mat(1, 2; 3, 4; delim: "[")
    vec(1, 2, delim: "|")
    vec(1, 2, delim: "||")
    vec(1, 2, delim: "{")
    mat(1, 2/3; 3, 4)
1 + #($λ n$)
λ'
cases(1 &"if" τ_i a, 3&"otherwise")
(a|b) (a | b) (a || b)
vec(1, 2, 3) mat(1, 2; 3, 4) (sum (0) x)+111+2^3/4+max_(i=1)^10(i^2)+max(x^2)+root(3, x)+sqrt(x)||{a} + "{text}" + floor(2)-(1|2) - (1 | 2)+upright(A) italic(A) bold(A) sans(A) frak(A) mono(A) bb(A) cal(A) & 1
[τ_i+1<μ ≤ τ_i] = cases(1 "if" τ_i+1<μ ≤ τ_i \ 0 "otherwise").
$)


#a

>> #raw(equation_to_latex(a))

>> #raw(equation_to_latex(a).replace(" ", "<SP>"))

repr: #raw(repr(a))

//#let x = 1em
//#("a" + repr(1em))

//$  #style(styles=>measure($1/2$, styles))  (1/2) ^(   #style(styles=>measure($1/2$, styles))   1/2)  $
//$ 1/2 + sqrt(sqrt(sqrt(2))) + \(sqrt(2)\)  $