"use strict";(self.webpackChunkdocusaurus=self.webpackChunkdocusaurus||[]).push([[667],{3905:function(e,r,n){n.d(r,{Zo:function(){return m},kt:function(){return f}});var t=n(7294);function a(e,r,n){return r in e?Object.defineProperty(e,r,{value:n,enumerable:!0,configurable:!0,writable:!0}):e[r]=n,e}function o(e,r){var n=Object.keys(e);if(Object.getOwnPropertySymbols){var t=Object.getOwnPropertySymbols(e);r&&(t=t.filter((function(r){return Object.getOwnPropertyDescriptor(e,r).enumerable}))),n.push.apply(n,t)}return n}function l(e){for(var r=1;r<arguments.length;r++){var n=null!=arguments[r]?arguments[r]:{};r%2?o(Object(n),!0).forEach((function(r){a(e,r,n[r])})):Object.getOwnPropertyDescriptors?Object.defineProperties(e,Object.getOwnPropertyDescriptors(n)):o(Object(n)).forEach((function(r){Object.defineProperty(e,r,Object.getOwnPropertyDescriptor(n,r))}))}return e}function i(e,r){if(null==e)return{};var n,t,a=function(e,r){if(null==e)return{};var n,t,a={},o=Object.keys(e);for(t=0;t<o.length;t++)n=o[t],r.indexOf(n)>=0||(a[n]=e[n]);return a}(e,r);if(Object.getOwnPropertySymbols){var o=Object.getOwnPropertySymbols(e);for(t=0;t<o.length;t++)n=o[t],r.indexOf(n)>=0||Object.prototype.propertyIsEnumerable.call(e,n)&&(a[n]=e[n])}return a}var p=t.createContext({}),c=function(e){var r=t.useContext(p),n=r;return e&&(n="function"==typeof e?e(r):l(l({},r),e)),n},m=function(e){var r=c(e.components);return t.createElement(p.Provider,{value:r},e.children)},u={inlineCode:"code",wrapper:function(e){var r=e.children;return t.createElement(t.Fragment,{},r)}},s=t.forwardRef((function(e,r){var n=e.components,a=e.mdxType,o=e.originalType,p=e.parentName,m=i(e,["components","mdxType","originalType","parentName"]),s=c(n),f=a,d=s["".concat(p,".").concat(f)]||s[f]||u[f]||o;return n?t.createElement(d,l(l({ref:r},m),{},{components:n})):t.createElement(d,l({ref:r},m))}));function f(e,r){var n=arguments,a=r&&r.mdxType;if("string"==typeof e||a){var o=n.length,l=new Array(o);l[0]=s;var i={};for(var p in r)hasOwnProperty.call(r,p)&&(i[p]=r[p]);i.originalType=e,i.mdxType="string"==typeof e?e:a,l[1]=i;for(var c=2;c<o;c++)l[c]=n[c];return t.createElement.apply(null,l)}return t.createElement.apply(null,n)}s.displayName="MDXCreateElement"},9547:function(e,r,n){n.r(r),n.d(r,{assets:function(){return m},contentTitle:function(){return p},default:function(){return f},frontMatter:function(){return i},metadata:function(){return c},toc:function(){return u}});var t=n(7462),a=n(3366),o=(n(7294),n(3905)),l=["components"],i={},p="RF Modeling for Terragraph Network Planning",c={unversionedId:"rf_modeling/README",id:"rf_modeling/README",title:"RF Modeling for Terragraph Network Planning",description:"This document provides an in-depth description of the RF modeling and",source:"@site/../docs/rf_modeling/README.md",sourceDirName:"rf_modeling",slug:"/rf_modeling/",permalink:"/terragraph-planner/rf_modeling/",draft:!1,tags:[],version:"current",frontMatter:{},sidebar:"docs",previous:{title:"Future Directions",permalink:"/terragraph-planner/algorithm/optimization/Future_Directions"},next:{title:"System Architecture & Topology",permalink:"/terragraph-planner/rf_modeling/System_Architecture_And_Topology"}},m={},u=[],s={toc:u};function f(e){var r=e.components,n=(0,a.Z)(e,l);return(0,o.kt)("wrapper",(0,t.Z)({},s,n,{components:r,mdxType:"MDXLayout"}),(0,o.kt)("h1",{id:"rf-modeling-for-terragraph-network-planning"},"RF Modeling for Terragraph Network Planning"),(0,o.kt)("p",null,"This document provides an in-depth description of the RF modeling and\nimplementation details used in Terragraph Planner's development process."),(0,o.kt)("p",null,"The tool takes certain key parameters as input that describe the functional\nrange of any manufacturer\u2019s equipment. These parameters cover the\nsubcomponents antenna and radio units. The input parameter list also\nextends to cover additional details such as propagation modeling assumptions\nand higher-layer capabilities."),(0,o.kt)("h1",{id:"table-of-contents"},"Table of Contents"),(0,o.kt)("ol",null,(0,o.kt)("li",{parentName:"ol"},(0,o.kt)("a",{parentName:"li",href:"/terragraph-planner/rf_modeling/System_Architecture_And_Topology"},"System Architecture & Topology")),(0,o.kt)("li",{parentName:"ol"},(0,o.kt)("a",{parentName:"li",href:"/terragraph-planner/rf_modeling/Antenna_Front_End"},"Antenna Front End"),(0,o.kt)("ol",{parentName:"li"},(0,o.kt)("li",{parentName:"ol"},(0,o.kt)("a",{parentName:"li",href:"/terragraph-planner/rf_modeling/Antenna_Front_End#single-beam-pattern"},"Single-beam Pattern")),(0,o.kt)("li",{parentName:"ol"},(0,o.kt)("a",{parentName:"li",href:"/terragraph-planner/rf_modeling/Antenna_Front_End#multi-beam-effects"},"Multi-beam Effects")),(0,o.kt)("li",{parentName:"ol"},(0,o.kt)("a",{parentName:"li",href:"/terragraph-planner/rf_modeling/Antenna_Front_End#multi-sector-capability"},"Multi-sector Capability")))),(0,o.kt)("li",{parentName:"ol"},(0,o.kt)("a",{parentName:"li",href:"/terragraph-planner/rf_modeling/Radio_Models"},"Radio Models"),(0,o.kt)("ol",{parentName:"li"},(0,o.kt)("li",{parentName:"ol"},(0,o.kt)("a",{parentName:"li",href:"/terragraph-planner/rf_modeling/Radio_Models#rf-front-end"},"RF Front End")),(0,o.kt)("li",{parentName:"ol"},(0,o.kt)("a",{parentName:"li",href:"/terragraph-planner/rf_modeling/Radio_Models#baseband"},"Baseband")))),(0,o.kt)("li",{parentName:"ol"},(0,o.kt)("a",{parentName:"li",href:"/terragraph-planner/rf_modeling/Propagation_Models"},"Propagation Models"),(0,o.kt)("ol",{parentName:"li"},(0,o.kt)("li",{parentName:"ol"},(0,o.kt)("a",{parentName:"li",href:"/terragraph-planner/rf_modeling/Propagation_Models#fspl"},"FSPL")),(0,o.kt)("li",{parentName:"ol"},(0,o.kt)("a",{parentName:"li",href:"/terragraph-planner/rf_modeling/Propagation_Models#gal"},"GAL")),(0,o.kt)("li",{parentName:"ol"},(0,o.kt)("a",{parentName:"li",href:"/terragraph-planner/rf_modeling/Propagation_Models#rain-loss"},"Rain Loss")))),(0,o.kt)("li",{parentName:"ol"},(0,o.kt)("a",{parentName:"li",href:"/terragraph-planner/rf_modeling/Link_Budget_Calculations"},"Link Budget Calculations"),(0,o.kt)("ol",{parentName:"li"},(0,o.kt)("li",{parentName:"ol"},(0,o.kt)("a",{parentName:"li",href:"/terragraph-planner/rf_modeling/Link_Budget_Calculations#rsl-calculation"},"RSL Calculation")),(0,o.kt)("li",{parentName:"ol"},(0,o.kt)("a",{parentName:"li",href:"/terragraph-planner/rf_modeling/Link_Budget_Calculations#sinr-calculation"},"SINR Calculation"))))))}f.isMDXComponent=!0}}]);