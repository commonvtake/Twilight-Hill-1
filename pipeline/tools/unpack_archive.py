"""Extract using libarchive; reject paths outside the destination and non-regular entries."""
import ctypes as c,pathlib,sys
lib=c.CDLL('libarchive.so.13')
for name,args,ret in [('archive_read_new',[],c.c_void_p),('archive_read_support_filter_all',[c.c_void_p],c.c_int),('archive_read_support_format_all',[c.c_void_p],c.c_int),('archive_read_open_filename',[c.c_void_p,c.c_char_p,c.c_size_t],c.c_int),('archive_read_next_header',[c.c_void_p,c.POINTER(c.c_void_p)],c.c_int),('archive_entry_pathname',[c.c_void_p],c.c_char_p),('archive_entry_filetype',[c.c_void_p],c.c_uint),('archive_entry_size',[c.c_void_p],c.c_int64),('archive_read_data',[c.c_void_p,c.c_void_p,c.c_size_t],c.c_ssize_t),('archive_error_string',[c.c_void_p],c.c_char_p),('archive_read_free',[c.c_void_p],c.c_int)]:
 f=getattr(lib,name);f.argtypes=args;f.restype=ret
root=pathlib.Path(sys.argv[2]).resolve();root.mkdir(parents=True,exist_ok=True)
a=lib.archive_read_new();lib.archive_read_support_filter_all(a);lib.archive_read_support_format_all(a)
assert lib.archive_read_open_filename(a,sys.argv[1].encode(),10240)==0
entry=c.c_void_p();buf=c.create_string_buffer(1024*1024)
try:
 while True:
  status=lib.archive_read_next_header(a,c.byref(entry))
  if status==1:break
  if status!=0:raise RuntimeError(lib.archive_error_string(a))
  name=lib.archive_entry_pathname(entry).decode();out=(root/name).resolve();expected=lib.archive_entry_size(entry)
  if not out.is_relative_to(root):raise ValueError('Unsafe path')
  typ=lib.archive_entry_filetype(entry)
  if typ==0o040000:out.mkdir(parents=True,exist_ok=True);continue
  if typ!=0o100000:raise ValueError('Unexpected type')
  out.parent.mkdir(parents=True,exist_ok=True)
  with out.open('wb') as f:
   while True:
    n=lib.archive_read_data(a,buf,len(buf))
    if n==0:break
    if n<0:raise RuntimeError(lib.archive_error_string(a))
    f.write(buf.raw[:n])
  if out.stat().st_size!=expected:raise ValueError('Size mismatch: '+name)
  print(name,expected,flush=True)
finally:lib.archive_read_free(a)
