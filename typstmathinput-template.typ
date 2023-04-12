#let sequence=$a b$.body.func()
#let alignpoint=$&$.body.func()
#let mathstyle=$upright(A)$.body.func()
#let space=$a b$.body.children.at(1).func()

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
#let nextstyle(x) = {
  assert(0<=x and x<=3)
  calc.min(x+1, scriptscriptstyle)
}
#let nextscriptstyle(x) = {
  calc.max(scriptstyle, nextstyle(x))
}
#let defaultstyleheight(x) = {if x>=scriptstyle{0.55} else {1}}

#let cat(style, ..a) = {
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

#let setheight(x, height) = {
  x.height=height
  x
}
#let prependbody(x, pre) = {
  x.body=pre+x.body
  x
}

#let equation_body_to_latex(x, style) = {cat(style, ..{
  if x.func()==sequence{
    for y in x.children{
      (equation_body_to_latex(y, style),)
    }
  }else if x.func()==math.lr{
    assert(x.body.func()==sequence)
    if x.body.children.len()<=2{
      for i, y in x.body.children{
        (equation_body_to_latex(y, style),)
      }
    }else{
      let tmp=cat(style, ..{
        for i, y in x.body.children{
          if i>0 and x.body.children.len()-1>i{
            (equation_body_to_latex(y, style),)
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
      (prependbody(equation_body_to_latex(x.body.children.at(0), style), bracketstyle),
      tmp,
      prependbody(equation_body_to_latex(x.body.children.at(-1), style), bracketstyle))
    }
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
  }else if x.func()==text{
    let content={
      let wrap_in_text
      if x.text.match(regex("^\\d+$"))!=none {
        wrap_in_text=false
      }else{
        wrap_in_text=x.text.clusters().len()>1
      }
      if wrap_in_text { "\\text{" }
      x.text
        .replace("{", "\\{")
        .replace("}", "\\}")
      if wrap_in_text { "}" }
    }
    if style==displaystyle and (content=="∑" or content=="∏"){
      content=setheight(cat(style, content), 1.4)
    }
    (content,)
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

}

//#import "/home/user202729/TeX/typstmathinput-template.typ": equation_to_latex
//#let a =($ (sum (0) x)+111+2^3/4+max_(i=1)^10(i^2)+max(x^2)+root(3, x)+sqrt(x)||{a} + "{text}" + floor(2)-(1|2) - (1 | 2)+upright(A) italic(A) bold(A) sans(A) frak(A) mono(A) bb(A) cal(A) & 1 $)
////#let a=($lr((1+2)) + (1+2)$)
//
//
//#a
//
//>> #raw(equation_to_latex(a))
//
//#repr(a)

//$  #style(styles=>measure($1/2$, styles))  (1/2) ^(   #style(styles=>measure($1/2$, styles))   1/2)  $
//$ 1/2 + sqrt(sqrt(sqrt(2))) + \(sqrt(2)\)  $
