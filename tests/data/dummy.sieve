require ["fileinto", "mailbox"];

# 1. INBOX.Print
if header :contains "subject" "Invoice" {
    fileinto "INBOX.Print";
    stop;
}

# 2. Trash
if header :contains "x-spam-flag" "YES" {
    fileinto "Trash";
    stop;
}
