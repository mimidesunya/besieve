require ["fileinto", "mailbox", "regex", "body"];

# 1. INBOX.RegEx
if header :regex "subject" "^[0-9]+$" {
    fileinto "INBOX.RegEx";
    stop;
}

# 2. INBOX.Prefix
if header :matches "subject" "Pre*" {
    fileinto "INBOX.Prefix";
    stop;
}

# 3. INBOX.Body
if body :contains "Keyword" {
    fileinto "INBOX.Body";
    stop;
}

# 4. INBOX.Case
if header :contains :comparator "i;octet" "subject" "Sensitive" {
    fileinto "INBOX.Case";
    stop;
}

# 5. Action Only
if header :contains "x-spam" "YES" {
    discard;
    stop;
}

# 6. INBOX.Copy
if header :contains "subject" "CopyMe" {
    fileinto "INBOX.Copy";
    keep;
    stop;
}
