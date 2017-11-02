from rest_framework import serializers

from core.models import Package, TransactionDetail


class PackageSerializer(serializers.ModelSerializer):
    class Meta:
        model = Package
        fields = ('amount', 'name')


    # def get_queryset(self):
    #     try:
    #         amount = self.kwargs['amount'].lower()
    #         print("Packages for %s"%amount)
    #         return Package.objects.filter(amount=amount)
    #     except:
    #         # todo: send out a 404
    #         print("No Players found for this quality :(")
    #         pass


class TransactionDetailSerializer(serializers.ModelSerializer):
    class Meta:
        model = TransactionDetail
        fields = ('id', 'account', 'sender', 'amount')