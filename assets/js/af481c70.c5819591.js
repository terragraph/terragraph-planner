"use strict";(self.webpackChunkdocusaurus=self.webpackChunkdocusaurus||[]).push([[95],{3905:function(t,e,a){a.d(e,{Zo:function(){return h},kt:function(){return k}});var i=a(7294);function n(t,e,a){return e in t?Object.defineProperty(t,e,{value:a,enumerable:!0,configurable:!0,writable:!0}):t[e]=a,t}function r(t,e){var a=Object.keys(t);if(Object.getOwnPropertySymbols){var i=Object.getOwnPropertySymbols(t);e&&(i=i.filter((function(e){return Object.getOwnPropertyDescriptor(t,e).enumerable}))),a.push.apply(a,i)}return a}function o(t){for(var e=1;e<arguments.length;e++){var a=null!=arguments[e]?arguments[e]:{};e%2?r(Object(a),!0).forEach((function(e){n(t,e,a[e])})):Object.getOwnPropertyDescriptors?Object.defineProperties(t,Object.getOwnPropertyDescriptors(a)):r(Object(a)).forEach((function(e){Object.defineProperty(t,e,Object.getOwnPropertyDescriptor(a,e))}))}return t}function l(t,e){if(null==t)return{};var a,i,n=function(t,e){if(null==t)return{};var a,i,n={},r=Object.keys(t);for(i=0;i<r.length;i++)a=r[i],e.indexOf(a)>=0||(n[a]=t[a]);return n}(t,e);if(Object.getOwnPropertySymbols){var r=Object.getOwnPropertySymbols(t);for(i=0;i<r.length;i++)a=r[i],e.indexOf(a)>=0||Object.prototype.propertyIsEnumerable.call(t,a)&&(n[a]=t[a])}return n}var p=i.createContext({}),m=function(t){var e=i.useContext(p),a=e;return t&&(a="function"==typeof t?t(e):o(o({},e),t)),a},h=function(t){var e=m(t.components);return i.createElement(p.Provider,{value:e},t.children)},c={inlineCode:"code",wrapper:function(t){var e=t.children;return i.createElement(i.Fragment,{},e)}},g=i.forwardRef((function(t,e){var a=t.components,n=t.mdxType,r=t.originalType,p=t.parentName,h=l(t,["components","mdxType","originalType","parentName"]),g=m(a),k=n,f=g["".concat(p,".").concat(k)]||g[k]||c[k]||r;return a?i.createElement(f,o(o({ref:e},h),{},{components:a})):i.createElement(f,o({ref:e},h))}));function k(t,e){var a=arguments,n=e&&e.mdxType;if("string"==typeof t||n){var r=a.length,o=new Array(r);o[0]=g;var l={};for(var p in e)hasOwnProperty.call(e,p)&&(l[p]=e[p]);l.originalType=t,l.mdxType="string"==typeof t?t:n,o[1]=l;for(var m=2;m<r;m++)o[m]=a[m];return i.createElement.apply(null,o)}return i.createElement.apply(null,a)}g.displayName="MDXCreateElement"},9884:function(t,e,a){a.r(e),a.d(e,{assets:function(){return h},contentTitle:function(){return p},default:function(){return k},frontMatter:function(){return l},metadata:function(){return m},toc:function(){return c}});var i=a(7462),n=a(3366),r=(a(7294),a(3905)),o=["components"],l={},p="Optimization",m={unversionedId:"algorithm/optimization/README",id:"algorithm/optimization/README",title:"Optimization",description:"This doc describes the TG Planner optimization workflow and algorithms. It",source:"@site/../docs/algorithm/optimization/README.md",sourceDirName:"algorithm/optimization",slug:"/algorithm/optimization/",permalink:"/terragraph-planner/algorithm/optimization/",draft:!1,editUrl:"https://github.com/terragraph/terragraph-planner/edit/main/docs/../docs/algorithm/optimization/README.md",tags:[],version:"current",frontMatter:{},sidebar:"docs",previous:{title:"Ellipsoidal Model",permalink:"/terragraph-planner/algorithm/line_of_sight/Ellipsoidal_Model"},next:{title:"Overview",permalink:"/terragraph-planner/algorithm/optimization/Overview"}},h={},c=[],g={toc:c};function k(t){var e=t.components,a=(0,n.Z)(t,o);return(0,r.kt)("wrapper",(0,i.Z)({},g,a,{components:e,mdxType:"MDXLayout"}),(0,r.kt)("h1",{id:"optimization"},"Optimization"),(0,r.kt)("p",null,"This doc describes the TG Planner optimization workflow and algorithms. It\nbegins with a high-level overview of optimization approach and then dives into\nthe specifics of the mathematical formulation."),(0,r.kt)("h1",{id:"table-of-contents"},"Table of Contents"),(0,r.kt)("ol",null,(0,r.kt)("li",{parentName:"ol"},(0,r.kt)("a",{parentName:"li",href:"/terragraph-planner/algorithm/optimization/Overview"},"Overview"),(0,r.kt)("ol",{parentName:"li"},(0,r.kt)("li",{parentName:"ol"},(0,r.kt)("a",{parentName:"li",href:"/terragraph-planner/algorithm/optimization/Overview#problem-modeling"},"Problem Modeling")),(0,r.kt)("li",{parentName:"ol"},(0,r.kt)("a",{parentName:"li",href:"/terragraph-planner/algorithm/optimization/Overview#high-level-formulation"},"High-Level Formulation")),(0,r.kt)("li",{parentName:"ol"},(0,r.kt)("a",{parentName:"li",href:"/terragraph-planner/algorithm/optimization/Overview#optimization-workflow"},"Optimization Workflow")),(0,r.kt)("li",{parentName:"ol"},(0,r.kt)("a",{parentName:"li",href:"/terragraph-planner/algorithm/optimization/Overview#network-analysis"},"Network Analysis")))),(0,r.kt)("li",{parentName:"ol"},(0,r.kt)("a",{parentName:"li",href:"/terragraph-planner/algorithm/optimization/Notation"},"Notation")),(0,r.kt)("li",{parentName:"ol"},(0,r.kt)("a",{parentName:"li",href:"/terragraph-planner/algorithm/optimization/Cost_Minimization"},"Cost Minimization"),(0,r.kt)("ol",{parentName:"li"},(0,r.kt)("li",{parentName:"ol"},(0,r.kt)("a",{parentName:"li",href:"/terragraph-planner/algorithm/optimization/Cost_Minimization#objective-function"},"Objective Function")),(0,r.kt)("li",{parentName:"ol"},(0,r.kt)("a",{parentName:"li",href:"/terragraph-planner/algorithm/optimization/Cost_Minimization#constraints"},"Constraints"),(0,r.kt)("ol",{parentName:"li"},(0,r.kt)("li",{parentName:"ol"},(0,r.kt)("a",{parentName:"li",href:"/terragraph-planner/algorithm/optimization/Cost_Minimization#minimum-coverage"},"Minimum Coverage")),(0,r.kt)("li",{parentName:"ol"},(0,r.kt)("a",{parentName:"li",href:"/terragraph-planner/algorithm/optimization/Cost_Minimization#flow-balance"},"Flow Balance")),(0,r.kt)("li",{parentName:"ol"},(0,r.kt)("a",{parentName:"li",href:"/terragraph-planner/algorithm/optimization/Cost_Minimization#flow-capacity"},"Flow Capacity")),(0,r.kt)("li",{parentName:"ol"},(0,r.kt)("a",{parentName:"li",href:"/terragraph-planner/algorithm/optimization/Cost_Minimization#flow-site"},"Flow Site")),(0,r.kt)("li",{parentName:"ol"},(0,r.kt)("a",{parentName:"li",href:"/terragraph-planner/algorithm/optimization/Cost_Minimization#time-division-multiplexing"},"Time Division Multiplexing")),(0,r.kt)("li",{parentName:"ol"},(0,r.kt)("a",{parentName:"li",href:"/terragraph-planner/algorithm/optimization/Cost_Minimization#polarity"},"Polarity")),(0,r.kt)("li",{parentName:"ol"},(0,r.kt)("a",{parentName:"li",href:"/terragraph-planner/algorithm/optimization/Cost_Minimization#co-located-sites"},"Co-Located Sites")))))),(0,r.kt)("li",{parentName:"ol"},(0,r.kt)("a",{parentName:"li",href:"/terragraph-planner/algorithm/optimization/Coverage_Maximization"},"Coverage Maximization"),(0,r.kt)("ol",{parentName:"li"},(0,r.kt)("li",{parentName:"ol"},(0,r.kt)("a",{parentName:"li",href:"/terragraph-planner/algorithm/optimization/Coverage_Maximization#objective-function"},"Objective Function")),(0,r.kt)("li",{parentName:"ol"},(0,r.kt)("a",{parentName:"li",href:"/terragraph-planner/algorithm/optimization/Coverage_Maximization#constraints"},"Constraints"),(0,r.kt)("ol",{parentName:"li"},(0,r.kt)("li",{parentName:"ol"},(0,r.kt)("a",{parentName:"li",href:"/terragraph-planner/algorithm/optimization/Coverage_Maximization#budget"},"Budget")),(0,r.kt)("li",{parentName:"ol"},(0,r.kt)("a",{parentName:"li",href:"/terragraph-planner/algorithm/optimization/Coverage_Maximization#adversarial-links"},"Adversarial Links")))))),(0,r.kt)("li",{parentName:"ol"},(0,r.kt)("a",{parentName:"li",href:"/terragraph-planner/algorithm/optimization/Redundancy_Optimization"},"Cost Minimization with Redundancy"),(0,r.kt)("ol",{parentName:"li"},(0,r.kt)("li",{parentName:"ol"},(0,r.kt)("a",{parentName:"li",href:"/terragraph-planner/algorithm/optimization/Redundancy_Optimization#objective-function"},"Objective Function")),(0,r.kt)("li",{parentName:"ol"},(0,r.kt)("a",{parentName:"li",href:"/terragraph-planner/algorithm/optimization/Redundancy_Optimization#decision-variables"},"Decision Variables")),(0,r.kt)("li",{parentName:"ol"},(0,r.kt)("a",{parentName:"li",href:"/terragraph-planner/algorithm/optimization/Redundancy_Optimization#redundancy-constraints"},"Redundancy Constraints"),(0,r.kt)("ol",{parentName:"li"},(0,r.kt)("li",{parentName:"ol"},(0,r.kt)("a",{parentName:"li",href:"/terragraph-planner/algorithm/optimization/Redundancy_Optimization#flow-site"},"Flow Site")),(0,r.kt)("li",{parentName:"ol"},(0,r.kt)("a",{parentName:"li",href:"/terragraph-planner/algorithm/optimization/Redundancy_Optimization#flow-balance"},"Flow Balance")),(0,r.kt)("li",{parentName:"ol"},(0,r.kt)("a",{parentName:"li",href:"/terragraph-planner/algorithm/optimization/Redundancy_Optimization#polarity"},"Polarity")))),(0,r.kt)("li",{parentName:"ol"},(0,r.kt)("a",{parentName:"li",href:"/terragraph-planner/algorithm/optimization/Redundancy_Optimization#two-phase-solution"},"Two Phase Solution"),(0,r.kt)("ol",{parentName:"li"},(0,r.kt)("li",{parentName:"ol"},(0,r.kt)("a",{parentName:"li",href:"/terragraph-planner/algorithm/optimization/Redundancy_Optimization#flow-balance-with-shortage"},"Flow Balance with Shortage")),(0,r.kt)("li",{parentName:"ol"},(0,r.kt)("a",{parentName:"li",href:"/terragraph-planner/algorithm/optimization/Redundancy_Optimization#relaxed-redundancy-objective-function"},"Relaxed Redundancy Objective Function")))),(0,r.kt)("li",{parentName:"ol"},(0,r.kt)("a",{parentName:"li",href:"/terragraph-planner/algorithm/optimization/Redundancy_Optimization#heuristic-acceleration"},"Heuristic Acceleration"),(0,r.kt)("ol",{parentName:"li"},(0,r.kt)("li",{parentName:"ol"},(0,r.kt)("a",{parentName:"li",href:"/terragraph-planner/algorithm/optimization/Redundancy_Optimization#delaunay-acceleration"},"Delaunay Acceleration")))))),(0,r.kt)("li",{parentName:"ol"},(0,r.kt)("a",{parentName:"li",href:"/terragraph-planner/algorithm/optimization/Interference_Minimization"},"Interference Minimization"),(0,r.kt)("ol",{parentName:"li"},(0,r.kt)("li",{parentName:"ol"},(0,r.kt)("a",{parentName:"li",href:"/terragraph-planner/algorithm/optimization/Interference_Minimization#objective-function"},"Objective Function")),(0,r.kt)("li",{parentName:"ol"},(0,r.kt)("a",{parentName:"li",href:"/terragraph-planner/algorithm/optimization/Interference_Minimization#constraints"},"Constraints"),(0,r.kt)("ol",{parentName:"li"},(0,r.kt)("li",{parentName:"ol"},(0,r.kt)("a",{parentName:"li",href:"/terragraph-planner/algorithm/optimization/Interference_Minimization#time-division-multiplexing"},"Time Division Multiplexing")),(0,r.kt)("li",{parentName:"ol"},(0,r.kt)("a",{parentName:"li",href:"/terragraph-planner/algorithm/optimization/Interference_Minimization#polarity"},"Polarity")),(0,r.kt)("li",{parentName:"ol"},(0,r.kt)("a",{parentName:"li",href:"/terragraph-planner/algorithm/optimization/Interference_Minimization#sector"},"Sector")),(0,r.kt)("li",{parentName:"ol"},(0,r.kt)("a",{parentName:"li",href:"/terragraph-planner/algorithm/optimization/Interference_Minimization#symmetric-link"},"Symmetric Link")),(0,r.kt)("li",{parentName:"ol"},(0,r.kt)("a",{parentName:"li",href:"/terragraph-planner/algorithm/optimization/Interference_Minimization#point-to-multipoint"},"Point-to-Multipoint")),(0,r.kt)("li",{parentName:"ol"},(0,r.kt)("a",{parentName:"li",href:"/terragraph-planner/algorithm/optimization/Interference_Minimization#cn-link"},"CN Link")),(0,r.kt)("li",{parentName:"ol"},(0,r.kt)("a",{parentName:"li",href:"/terragraph-planner/algorithm/optimization/Interference_Minimization#deployment-guidelines"},"Deployment Guidelines")),(0,r.kt)("li",{parentName:"ol"},(0,r.kt)("a",{parentName:"li",href:"/terragraph-planner/algorithm/optimization/Interference_Minimization#interference"},"Interference")))),(0,r.kt)("li",{parentName:"ol"},(0,r.kt)("a",{parentName:"li",href:"/terragraph-planner/algorithm/optimization/Interference_Minimization#multi-channel-constraints"},"Multi-Channel Constraints"),(0,r.kt)("ol",{parentName:"li"},(0,r.kt)("li",{parentName:"ol"},(0,r.kt)("a",{parentName:"li",href:"/terragraph-planner/algorithm/optimization/Interference_Minimization#multi-channel-sector"},"Multi-Channel Sector")),(0,r.kt)("li",{parentName:"ol"},(0,r.kt)("a",{parentName:"li",href:"/terragraph-planner/algorithm/optimization/Interference_Minimization#multi-channel-deployment-guidelines"},"Multi-Channel Deployment Guidelines")),(0,r.kt)("li",{parentName:"ol"},(0,r.kt)("a",{parentName:"li",href:"/terragraph-planner/algorithm/optimization/Interference_Minimization#multi-channel-time-division-multiplexing"},"Multi-Channel Time Division Multiplexing")),(0,r.kt)("li",{parentName:"ol"},(0,r.kt)("a",{parentName:"li",href:"/terragraph-planner/algorithm/optimization/Interference_Minimization#multi-channel-interference"},"Multi-Channel Interference")))))),(0,r.kt)("li",{parentName:"ol"},(0,r.kt)("a",{parentName:"li",href:"/terragraph-planner/algorithm/optimization/Connected_Demand"},"Connected Demand Site Optimization"),(0,r.kt)("ol",{parentName:"li"},(0,r.kt)("li",{parentName:"ol"},(0,r.kt)("a",{parentName:"li",href:"/terragraph-planner/algorithm/optimization/Connected_Demand#objective-function"},"Objective Function")),(0,r.kt)("li",{parentName:"ol"},(0,r.kt)("a",{parentName:"li",href:"/terragraph-planner/algorithm/optimization/Connected_Demand#decision-variables"},"Decision Variables")),(0,r.kt)("li",{parentName:"ol"},(0,r.kt)("a",{parentName:"li",href:"/terragraph-planner/algorithm/optimization/Connected_Demand#cost-minimization-and-coverage-maximization-constraints"},"Cost Minimization and Coverage Maximization Constraints"),(0,r.kt)("ol",{parentName:"li"},(0,r.kt)("li",{parentName:"ol"},(0,r.kt)("a",{parentName:"li",href:"/terragraph-planner/algorithm/optimization/Connected_Demand#flow-balance"},"Flow Balance")),(0,r.kt)("li",{parentName:"ol"},(0,r.kt)("a",{parentName:"li",href:"/terragraph-planner/algorithm/optimization/Connected_Demand#flow-capacity"},"Flow Capacity")),(0,r.kt)("li",{parentName:"ol"},(0,r.kt)("a",{parentName:"li",href:"/terragraph-planner/algorithm/optimization/Connected_Demand#flow-site"},"Flow Site")),(0,r.kt)("li",{parentName:"ol"},(0,r.kt)("a",{parentName:"li",href:"/terragraph-planner/algorithm/optimization/Connected_Demand#polarity"},"Polarity")),(0,r.kt)("li",{parentName:"ol"},(0,r.kt)("a",{parentName:"li",href:"/terragraph-planner/algorithm/optimization/Connected_Demand#adversarial-links"},"Adversarial Links")),(0,r.kt)("li",{parentName:"ol"},(0,r.kt)("a",{parentName:"li",href:"/terragraph-planner/algorithm/optimization/Connected_Demand#flow-demand"},"Flow Demand")))),(0,r.kt)("li",{parentName:"ol"},(0,r.kt)("a",{parentName:"li",href:"/terragraph-planner/algorithm/optimization/Connected_Demand#interference-minimization-constraints"},"Interference Minimization Constraints"),(0,r.kt)("ol",{parentName:"li"},(0,r.kt)("li",{parentName:"ol"},(0,r.kt)("a",{parentName:"li",href:"/terragraph-planner/algorithm/optimization/Connected_Demand#flow-link"},"Flow Link")))))),(0,r.kt)("li",{parentName:"ol"},(0,r.kt)("a",{parentName:"li",href:"/terragraph-planner/algorithm/optimization/Flow_Optimization"},"Flow Optimization"),(0,r.kt)("ol",{parentName:"li"},(0,r.kt)("li",{parentName:"ol"},(0,r.kt)("a",{parentName:"li",href:"/terragraph-planner/algorithm/optimization/Flow_Optimization#objective-function"},"Objective Function")),(0,r.kt)("li",{parentName:"ol"},(0,r.kt)("a",{parentName:"li",href:"/terragraph-planner/algorithm/optimization/Flow_Optimization#constraints"},"Constraints"),(0,r.kt)("ol",{parentName:"li"},(0,r.kt)("li",{parentName:"ol"},(0,r.kt)("a",{parentName:"li",href:"/terragraph-planner/algorithm/optimization/Flow_Optimization#flow-balance"},"Flow Balance")))))),(0,r.kt)("li",{parentName:"ol"},(0,r.kt)("a",{parentName:"li",href:"/terragraph-planner/algorithm/optimization/Future_Directions"},"Future Directions"),(0,r.kt)("ol",{parentName:"li"},(0,r.kt)("li",{parentName:"ol"},(0,r.kt)("a",{parentName:"li",href:"/terragraph-planner/algorithm/optimization/Future_Directions#p2mp-constraints-in-site-selection"},"P2MP Constraints in Site Selection")),(0,r.kt)("li",{parentName:"ol"},(0,r.kt)("a",{parentName:"li",href:"/terragraph-planner/algorithm/optimization/Future_Directions#multi-channel-link-capacity-and-interference"},"Multi-Channel Link Capacity and Interference")),(0,r.kt)("li",{parentName:"ol"},(0,r.kt)("a",{parentName:"li",href:"/terragraph-planner/algorithm/optimization/Future_Directions#sector-orientation"},"Sector Orientation")),(0,r.kt)("li",{parentName:"ol"},(0,r.kt)("a",{parentName:"li",href:"/terragraph-planner/algorithm/optimization/Future_Directions#pop-placement"},"POP Placement")),(0,r.kt)("li",{parentName:"ol"},(0,r.kt)("a",{parentName:"li",href:"/terragraph-planner/algorithm/optimization/Future_Directions#variable-pop-capacity"},"Variable POP Capacity")),(0,r.kt)("li",{parentName:"ol"},(0,r.kt)("a",{parentName:"li",href:"/terragraph-planner/algorithm/optimization/Future_Directions#uplink-modeling"},"Uplink Modeling")),(0,r.kt)("li",{parentName:"ol"},(0,r.kt)("a",{parentName:"li",href:"/terragraph-planner/algorithm/optimization/Future_Directions#channel-bonding"},"Channel Bonding")),(0,r.kt)("li",{parentName:"ol"},(0,r.kt)("a",{parentName:"li",href:"/terragraph-planner/algorithm/optimization/Future_Directions#a-note-on-run-to-run-reproducibility"},"A Note on Run-to-Run Reproducibility"))))))}k.isMDXComponent=!0}}]);