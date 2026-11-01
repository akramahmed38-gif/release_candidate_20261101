"""Reusable test-only registry checks, independent of fact/service identifiers."""
import hashlib
def sha(value):return hashlib.sha256(value).hexdigest()
def load_records(definition,source_root,authorized):
    accepted={};rejected={}
    for f in definition['facts']:
        fid=f['fact_id'];reason=None
        if fid not in authorized:reason='not_authorized_for_fixture'
        elif fid not in definition.get('review_bindings',{}):reason='unreviewed_source_binding'
        elif any(f.get(k)!=v for k,v in definition['review_bindings'][fid].items()):reason='replacement_requires_source_and_language_review'
        elif any(f.get(k) for k in ['normal_runtime_eligible','business_approved','human_fidelity_approved']):reason='approval_boundary'
        elif not f.get('english') or not f.get('arabic'):reason='missing_language_view'
        elif any(sha(f[k].encode())!=f.get(k+'_sha256') for k in ['arabic','english']):reason='view_fingerprint'
        elif f.get('view_source_sha256',f['source_sha256'])!=f['source_sha256']:reason='source_revision_requires_new_view_review'
        elif f.get('revision',1)!=f.get('authorized_fixture_revision',1):reason='revision_requires_explicit_fixture_reauthorization'
        else:
            try:
                path=(source_root/f['source_document']).resolve();path.relative_to(source_root.resolve())
                if sha(path.read_bytes())!=f['source_sha256']:reason='source_version'
            except (OSError,ValueError):reason='source_unavailable'
        if reason:rejected[fid]=reason
        else:accepted[fid]=f
    changed=True
    while changed:
        changed=False
        for fid,f in list(accepted.items()):
            if any(d not in accepted for d in f.get('dependencies',[])):
                del accepted[fid];rejected[fid]='missing_dependency';changed=True
    return accepted,rejected
