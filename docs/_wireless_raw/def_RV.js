RV=e=>e.length>7||e.length<4? {
  r:0,g:0,b:0
}:e.length===4? {
  r:parseInt(e[1]+e[1],16),g:parseInt(e[2]+e[2],16),b:parseInt(e[3]+e[3],16)
}: {
  r:parseInt(e.slice(1,3),16),g:parseInt(e.slice(3,5),16),b:parseInt(e.slice(5,7),16)
}