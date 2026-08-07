use proc_macro::TokenStream;
use proc_macro2::Literal;
use quote::quote;
use syn::{Data, DeriveInput, Fields, Lit, parse_macro_input};

struct FieldMeta {
    ident: syn::Ident,
    ty: syn::Type,
    key: String,
    default: Option<syn::Expr>,
    is_optional: bool,
}

#[expect(
    clippy::expect_used,
    reason = "proc-macro: misuse (unnamed fields) is reported by rustc as a compile error at the derive site"
)]
fn parse_field_meta(field: &syn::Field) -> FieldMeta {
    let ident = field.ident.clone().expect("FromPyDict requires named fields");
    let ty = field.ty.clone();
    let mut key = ident.to_string();
    let mut default: Option<syn::Expr> = None;
    let mut is_optional = false;

    for attr in &field.attrs {
        if !attr.path().is_ident("pyo3") {
            continue;
        }
        let _ = attr.parse_nested_meta(|meta| {
            if meta.path.is_ident("key") {
                let value = meta.value()?;
                let s: Lit = value.parse()?;
                if let Lit::Str(lit_str) = s {
                    key = lit_str.value();
                }
            } else if meta.path.is_ident("default") {
                let value = meta.value()?;
                default = Some(value.parse()?);
            } else if meta.path.is_ident("optional") {
                is_optional = true;
            }
            Ok(())
        });
    }

    FieldMeta {
        ident,
        ty,
        key,
        default,
        is_optional,
    }
}

fn is_optional_type(ty: &syn::Type) -> bool {
    if let syn::Type::Path(type_path) = ty
        && let Some(segment) = type_path.path.segments.last()
    {
        return segment.ident == "Option";
    }
    false
}

fn is_str_type(ty: &syn::Type) -> bool {
    if let syn::Type::Path(type_path) = ty
        && let Some(segment) = type_path.path.segments.last()
    {
        let name = segment.ident.to_string();
        return name == "String" || name == "str" || name == "OsString";
    }
    false
}

fn is_bool_type(ty: &syn::Type) -> bool {
    if let syn::Type::Path(type_path) = ty
        && let Some(segment) = type_path.path.segments.last()
    {
        return segment.ident == "bool";
    }
    false
}

fn is_f64_type(ty: &syn::Type) -> bool {
    if let syn::Type::Path(type_path) = ty
        && let Some(segment) = type_path.path.segments.last()
    {
        let name = segment.ident.to_string();
        return name == "f64" || name == "f32" || name == "i64" || name == "i32";
    }
    false
}

#[proc_macro_derive(FromPyDict, attributes(pyo3))]
pub fn derive_from_py_dict(input: TokenStream) -> TokenStream {
    let input = parse_macro_input!(input as DeriveInput);
    let struct_name = &input.ident;

    let fields = match &input.data {
        Data::Struct(data) => match &data.fields {
            Fields::Named(fields) => &fields.named,
            _ => panic!("FromPyDict requires named fields"),
        },
        _ => panic!("FromPyDict can only be derived for structs"),
    };

    let metas: Vec<FieldMeta> = fields.iter().map(parse_field_meta).collect();

    let extractors: Vec<_> = metas.iter().map(|m| {
        let ident = &m.ident;
        let key = &m.key;
        let key_lit = Literal::string(key);

        if m.is_optional || is_optional_type(&m.ty) {
            if is_str_type(&m.ty) {
                quote! {
                    let #ident: Option<String> = temper_py_bridge::extract_opt_str(dict, #key_lit)?;
                }
            } else if is_bool_type(&m.ty) {
                quote! {
                    let #ident: Option<bool> = temper_py_bridge::extract_opt_bool(dict, #key_lit)?;
                }
            } else if is_f64_type(&m.ty) {
                quote! {
                    let #ident: Option<f64> = temper_py_bridge::extract_opt_f64(dict, #key_lit)?;
                }
            } else {
                let ty = &m.ty;
                quote! {
                    let #ident: #ty = {
                        let val: Option<pyo3::Bound<'_, pyo3::PyAny>> = dict.get_item(#key_lit)?;
                        match val {
                            Some(v) if !v.is_none() => Some(v.extract()?),
                            _ => None,
                        }
                    };
                }
            }
        } else if is_str_type(&m.ty) {
            quote! {
                let #ident: String = temper_py_bridge::extract_str(dict, #key_lit)?;
            }
        } else if is_bool_type(&m.ty) {
            if let Some(ref default) = m.default {
                quote! {
                    let #ident: bool = {
                        match dict.get_item(#key_lit)? {
                            Some(v) if !v.is_none() => v.extract()?,
                            _ => #default,
                        }
                    };
                }
            } else {
                quote! {
                    let #ident: bool = temper_py_bridge::extract_bool(dict, #key_lit)?;
                }
            }
        } else if is_f64_type(&m.ty) {
            if let Some(ref default) = m.default {
                quote! {
                    let #ident: f64 = temper_py_bridge::extract_f64(dict, #key_lit, #default)?;
                }
            } else {
                quote! {
                    let #ident: f64 = temper_py_bridge::extract_f64_required(dict, #key_lit)?;
                }
            }
        } else {
            let ty = &m.ty;
            quote! {
                let #ident: #ty = {
                    let val = dict.get_item(#key_lit)?
                        .ok_or_else(|| PyErr::new::<pyo3::exceptions::PyValueError, _>(
                            format!("missing required key: {}", #key_lit)
                        ))?;
                    val.extract()?
                };
            }
        }
    }).collect();

    let field_names: Vec<_> = metas.iter().map(|m| &m.ident).collect();

    let expanded = quote! {
        impl #struct_name {
            #[allow(unused_imports)]
            pub fn from_py_dict(dict: &pyo3::Bound<'_, pyo3::types::PyDict>) -> pyo3::PyResult<Self> {
                use pyo3::prelude::*;
                #[allow(unused_imports)]
                use temper_py_bridge::DictExtract;
                #(#extractors)*
                Ok(Self {
                    #(#field_names,)*
                })
            }
        }
    };

    TokenStream::from(expanded)
}

#[proc_macro_derive(ToPyDict, attributes(pyo3))]
pub fn derive_to_py_dict(input: TokenStream) -> TokenStream {
    let input = parse_macro_input!(input as DeriveInput);
    let struct_name = &input.ident;

    let fields = match &input.data {
        Data::Struct(data) => match &data.fields {
            Fields::Named(fields) => &fields.named,
            _ => panic!("ToPyDict requires named fields"),
        },
        _ => panic!("ToPyDict can only be derived for structs"),
    };

    let metas: Vec<FieldMeta> = fields.iter().map(parse_field_meta).collect();

    let set_items: Vec<_> = metas.iter().map(|m| {
        let ident = &m.ident;
        let key = &m.key;
        let key_lit = Literal::string(key);

        if m.is_optional || is_optional_type(&m.ty) {
            quote! {
                if let Some(ref val) = self.#ident {
                    d.set_item(#key_lit, val)?;
                }
            }
        } else {
            quote! {
                d.set_item(#key_lit, &self.#ident)?;
            }
        }
    }).collect();

    let expanded = quote! {
        impl #struct_name {
            #[allow(unused_imports)]
            pub fn to_py_dict(&self, py: pyo3::Python<'_>) -> pyo3::PyResult<pyo3::PyObject> {
                use pyo3::prelude::*;
                use pyo3::types::PyDict;
                let d = PyDict::new(py);
                #(#set_items)*
                Ok(d.into())
            }
        }
    };

    TokenStream::from(expanded)
}
