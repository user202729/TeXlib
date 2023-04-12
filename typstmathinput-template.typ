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

#let equation_body_to_latex(x) = {
  if x.func()==sequence{
    for y in x.children{
      equation_body_to_latex(y)
    }
  }else if x.func()==math.lr{
    assert(x.body.func()==sequence)
    for i, y in x.body.children{
      if i==0{ "\\left" }
      if i==x.body.children.len()-1{ "\\right" }
      equation_body_to_latex(y)
    }
  }else if x.func()==math.op{
    if x.limits{
      "\\operatorname*{"
    }else{
      "\\operatorname{"
    }
    x.text
    "}"
  }else if x.func()==space{
    //"\\ "
  }else if x.func()==text{
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
  }else if x.func()==math.root{
    "\\sqrt"
    if x.has("index"){
      "[{"
      equation_body_to_latex(x.index)
      "}]"
    }
    "{"
    equation_body_to_latex(x.radicand)
    "}"
  }else if x.func()==math.attach{
    equation_body_to_latex(x.base)
    if x.has("top"){
      "^{"
      equation_body_to_latex(x.top)
      "}"
    }
    if x.has("bottom"){
      "_{"
      equation_body_to_latex(x.bottom)
      "}"
    }
  }else if x.func()==math.frac{
    "\\frac{"
    equation_body_to_latex(x.num)
    "}{"
    equation_body_to_latex(x.denom)
    "}"
  }else if x.func()==mathstyle{
    if x.has("bold"){
      assert(not x.has("italic"))
      assert(not x.has("variant"))
      assert(x.bold)
      "\\mathbf{"
      equation_body_to_latex(x.body)
      "}"
    }else if x.has("italic"){
      assert(not x.has("variant"))
      if x.italic{
        "\\mathit{"
        equation_body_to_latex(x.body)
        "}"
      }else{
        "\\mathrm{"
        equation_body_to_latex(x.body)
        "}"
      }
    }else{
      variant_to_latex_lookup.at(x.variant)
      "{"
      equation_body_to_latex(x.body)
      "}"
    }
  }else if x.func()==alignpoint{
    " &"
  }else if x.func()==linebreak{
    " \\\\"
  }else{
    "\\text{(unknown func "
    repr(x.func())
    ")}"
  }
}

#let equation_to_latex(x) = {
  assert(x.func()==math.equation)
  if x.block {
    let body=equation_body_to_latex(x.body)
    if body.match(" &")!=none or body.match(" \\\\")!=none{
      "\\begin{align*}\\typstmathinputnormcat " + body + "\\end{align*}"
    } else {
      "\\[\\typstmathinputnormcat " + body + "\\]"
    }
  } else {
    "\\(\\typstmathinputnormcat " + equation_body_to_latex(x.body) + "\\)" // for usage from TeX don't use active `$` which recursively call the original function
  }
}
